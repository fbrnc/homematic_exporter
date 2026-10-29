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
            mock.patch.object(processor, 'run_rega_script', return_value=[]), \
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


def device(address, device_type):
    return {'ADDRESS': address, 'PARENT': '', 'TYPE': device_type, 'PARENT_TYPE': '', 'PARAMSETS': ['MASTER'], 'CHILDREN': []}


def test_last_event(processor):
    devices = [device('BTN0002', 'HM-PB-6-WM55'), device('BTN0003', 'HM-PB-6-WM55'), device('UNS0001', 'HM-UNSUPPORTED'),
               channel('BTN0002:1', 'HM-PB-6-WM55', 'KEY')]
    lines = ['BTN0002\t1793251864', 'BTN0003\t0', 'UNS0001\t1793251864', 'OTHER01\t1793251864', 'BidCoS-RF\t']

    with mock.patch.object(processor, 'supported_device_types', ['HM-PB-6-WM55']), \
            mock.patch.object(processor, 'run_rega_script', return_value=lines):
        processor.generate_last_event_metrics(devices)

    def value(address):
        return REGISTRY.get_sample_value('homematic_last_event_timestamp_seconds',
                                         {'ccu': CCU, 'device': address, 'device_type': 'HM-PB-6-WM55', 'mapped_name': address})
    assert value('BTN0002') == 1793251864
    assert value('BTN0003') is None
    lines = [line for line in generate_latest().decode().splitlines() if line.startswith('homematic_last_event_timestamp_seconds{')]
    assert len(lines) == 1


def test_last_event_failure_does_not_raise(processor):
    with mock.patch.object(processor, 'run_rega_script', side_effect=OSError('Connection refused')):
        processor.generate_last_event_metrics([])


def test_messages(processor):
    lines = ['S\tAL-ACT0002:0.STICKY_UNREACH', 'S\tAL-0009DD89A529E2:0.UNREACH', 'S\tsomething else',
             'A\tAlarmzone 1\t0', 'A\tWatchDog-Alarm\t1']
    with mock.patch.object(processor, 'run_rega_script', return_value=lines):
        processor.generate_message_metrics()

    def message(address, message_type):
        return REGISTRY.get_sample_value('homematic_service_message',
                                         {'ccu': CCU, 'device': address, 'mapped_name': address, 'type': message_type})
    assert message('ACT0002', 'STICKY_UNREACH') == 1
    assert message('0009DD89A529E2', 'UNREACH') == 1
    assert REGISTRY.get_sample_value('homematic_alarm_message', {'ccu': CCU, 'name': 'Alarmzone 1'}) == 0
    assert REGISTRY.get_sample_value('homematic_alarm_message', {'ccu': CCU, 'name': 'WatchDog-Alarm'}) == 1

    # acknowledged messages disappear
    with mock.patch.object(processor, 'run_rega_script', return_value=['S\tAL-0009DD89A529E2:0.UNREACH', 'A\tWatchDog-Alarm\t0']):
        processor.generate_message_metrics()
    assert message('ACT0002', 'STICKY_UNREACH') is None
    assert message('0009DD89A529E2', 'UNREACH') == 1
    assert REGISTRY.get_sample_value('homematic_alarm_message', {'ccu': CCU, 'name': 'WatchDog-Alarm'}) == 0


def test_messages_failure_does_not_raise(processor):
    with mock.patch.object(processor, 'run_rega_script', side_effect=OSError('Connection refused')):
        processor.generate_message_metrics()
