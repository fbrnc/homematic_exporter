import xmlrpc.client
from unittest import mock

import pytest
from prometheus_client import REGISTRY, generate_latest

from exporter import HomematicMetricsProcessor

CCU = 'ccu.example'


@pytest.fixture(scope='module')
def processor():
    # Metrics are registered in the global registry, so only one instance per test run.
    return HomematicMetricsProcessor(CCU, 2001, None, 60, 30, None)


def channel(address, parent_type, channel_type='MAINTENANCE'):
    return {'ADDRESS': address, 'PARENT': address.split(':')[0], 'TYPE': channel_type,
            'PARENT_TYPE': parent_type, 'PARAMSETS': ['MASTER', 'VALUES'], 'CHILDREN': []}


def test_interface_metrics(processor):
    interfaces = [
        {'ADDRESS': 'IF0001', 'TYPE': 'CCU2', 'CONNECTED': True, 'DUTY_CYCLE': 53},
        {'ADDRESS': 'IF0002', 'TYPE': 'HMIP_CCU2', 'CONNECTED': False, 'DUTY_CYCLE': 7},
    ]
    with mock.patch.object(processor, 'fetch_interfaces_list', return_value=interfaces):
        processor.generate_interface_metrics()

    labels = {'ccu': CCU, 'interface': 'IF0001', 'interface_type': 'CCU2'}
    assert REGISTRY.get_sample_value('homematic_interface_duty_cycle', labels) == 53
    assert REGISTRY.get_sample_value('homematic_interface_connected', labels) == 1
    labels = {'ccu': CCU, 'interface': 'IF0002', 'interface_type': 'HMIP_CCU2'}
    assert REGISTRY.get_sample_value('homematic_interface_duty_cycle', labels) == 7
    assert REGISTRY.get_sample_value('homematic_interface_connected', labels) == 0


def test_interface_failure_does_not_raise(processor):
    with mock.patch.object(processor, 'fetch_interfaces_list', side_effect=xmlrpc.client.Fault(-1, 'Unknown method')):
        processor.generate_interface_metrics()
    with mock.patch.object(processor, 'fetch_interfaces_list', side_effect=OSError('Connection refused')):
        processor.generate_interface_metrics()


def test_channels_only(processor):
    devices = [channel('ACT0001:0', 'HM-LC-Sw4-PCB')] + \
        [channel('ACT0001:{}'.format(i), 'HM-LC-Sw4-PCB', 'SWITCH') for i in range(1, 5)] + \
        [channel('BTN0001:0', 'HM-PB-6-WM55'), channel('BTN0001:1', 'HM-PB-6-WM55', 'KEY')]
    description = {'UNREACH': {'TYPE': 'BOOL'}}

    with mock.patch.object(processor, 'supported_device_types', ['HM-LC-Sw4-PCB', 'HM-PB-6-WM55']), \
            mock.patch.object(processor, 'channels_only', {'HM-LC-Sw4-PCB': [0]}), \
            mock.patch.object(processor, 'fetch_interfaces_list', return_value=[]), \
            mock.patch.object(processor, 'fetch_devices_list', return_value=devices), \
            mock.patch.object(processor, 'fetch_param_set_description', return_value=description) as fetch_description, \
            mock.patch.object(processor, 'fetch_param_set', return_value={'UNREACH': False}) as fetch:
        processor.generate_metrics()

    read = [call.args[0] for call in fetch.call_args_list]
    assert read == ['ACT0001:0', 'BTN0001:0', 'BTN0001:1']
    assert [call.args[0] for call in fetch_description.call_args_list] == read


def test_enum_with_empty_states_has_no_duplicates(processor):
    states = ['NO_ERROR', '', '', '', '', '', '', 'SABOTAGE']
    processor.process_enum('SCO0001:1', 'SHUTTER_CONTACT', 'SCO0001', 'HM-Sec-SCo', 'ERROR', 0, states)

    lines = [line for line in generate_latest().decode().splitlines() if line.startswith('homematic_error_set{')]
    assert len(lines) == len(states)
    assert len(set(lines)) == len(lines)
    labels = {'ccu': CCU, 'device': 'SCO0001:1', 'device_type': 'SHUTTER_CONTACT', 'parent_device_type': 'HM-Sec-SCo',
              'mapped_name': 'SCO0001:1'}
    assert REGISTRY.get_sample_value('homematic_error_set', dict(labels, homematic_error_set='NO_ERROR')) == 1
    assert REGISTRY.get_sample_value('homematic_error_set', dict(labels, homematic_error_set='SABOTAGE')) == 0

    processor.process_enum('SCO0001:1', 'SHUTTER_CONTACT', 'SCO0001', 'HM-Sec-SCo', 'ERROR', 7, states)
    assert REGISTRY.get_sample_value('homematic_error_set', dict(labels, homematic_error_set='SABOTAGE')) == 1
