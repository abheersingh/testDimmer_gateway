from bluepy.btle import Scanner, UUID, Peripheral, DefaultDelegate, BTLEException
import json
import bluetooth._bluetooth as _bt
import struct 
import thread
import threading
from Light_devices import Light_device
from Test_devices import Test_device
#from urllib3 import MaxRetryError
from urllib3.exceptions import MaxRetryError
import binascii
import time

gatewayCommandList = {'sendACK':'\x00', 'getDeviceStatus':'\x02', 
                        'getDeviceList':'\x04', 'turnDeviceOn':'\x06', 
                        'turnDeviceOff':'\x08', 'gatewayBusy':'\x0A', 
                        'gatewayReady':'\x0C', 'setBrightness': '\x0E', 
                        'getBrightness': '\x10'}

adapterCommandList = {'Ack':'\x01', 'adapterBusy':'\x03', 'adapterReady':'\x05',
                      'deviceList':'\x07', 'deviceIsOn':'\x09', 'deviceIsOff':'\x0B',
                      'brightnessLevel':'\x0D',
                      'error':'\xFF'}

def read_local_bdaddr():
    hci_sock = _bt.hci_open_dev(0)
    old_filter = hci_sock.getsockopt( _bt.SOL_HCI, _bt.HCI_FILTER, 14)
    flt = _bt.hci_filter_new()
    opcode = _bt.cmd_opcode_pack(_bt.OGF_INFO_PARAM, 
            _bt.OCF_READ_BD_ADDR)
    _bt.hci_filter_set_ptype(flt, _bt.HCI_EVENT_PKT)
    _bt.hci_filter_set_event(flt, _bt.EVT_CMD_COMPLETE)
    _bt.hci_filter_set_opcode(flt, opcode)
    hci_sock.setsockopt( _bt.SOL_HCI, _bt.HCI_FILTER, flt )

    _bt.hci_send_cmd(hci_sock, _bt.OGF_INFO_PARAM, _bt.OCF_READ_BD_ADDR )

    pkt = hci_sock.recv(255)

    status,raw_bdaddr = struct.unpack("xxxxxxB6s", pkt)
    assert status == 0

    t = [ "%02X" % ord(b) for b in raw_bdaddr ]
    t.reverse()
    bdaddr = ":".join(t)

    # restore old filter
    hci_sock.setsockopt( _bt.SOL_HCI, _bt.HCI_FILTER, old_filter )
    return bdaddr

def initialize_bluetooth():
    with open("config.json", 'r') as config_file:
        BT_Adapter.config = json.load(config_file)['Bluetooth']    
        print BT_Adapter.config
    return read_local_bdaddr()

class BT_Adapter:
    config = []
    def __init__(self, MAC, Gateway_MAC):
        self.MAC = MAC.encode('utf-8')
        self.Gateway_MAC = Gateway_MAC
        self.test_device=Test_device()
        self.light_device=Light_device(0,self.Gateway_MAC,self.MAC)
        self.peripheral = Peripheral(MAC)
        self.command_char = None
        self.brightness_level_char = None
        self.recv_brightness_level = None
        self.recv_command = None
        self.thread_enable = False
        self.thread_handle = None
        self.lock = threading.Lock()
        self.disconnect_count = 0
        
    def ble_notification_handle(self, cHandle, data):
        print cHandle
        
        self.recv_command = data
        print "Command received ascii: %s" % (binascii.b2a_hex(data)) 
        print 'Command received original: %d' %(ord(self.recv_command))   
        brightness_level  = self.brightness_level_char.read()[::-1]
        print 'Brightness level ascii:', binascii.b2a_hex(brightness_level)
        print 'Brightness level original: %d' %(ord(brightness_level))
        self.recv_brightness_level = ord(brightness_level)
        self.handle_adapter_command() 
        
        
    def handle_adapter_command(self):
        global adapterCommandList
        if self.recv_command == adapterCommandList['deviceIsOn']: 
            self.light_device.set_state('ON')
            self.light_device.set_brightness(self.recv_brightness_level)
            print 'Status On command'          
        elif self.recv_command == adapterCommandList['deviceIsOff']:
            self.light_device.set_state('OFF')
            self.light_device.set_brightness(self.recv_brightness_level)
            print 'Status Off command'
        elif self.recv_command == adapterCommandList['brightnessLevel']:
            self.light_device.set_brightness(self.recv_brightness_level)
            print 'Brightness command'
        self.light_device.send_device_data()
            
    def enable_notification(self):
        retry = 2
        while retry > 0:
            try:
                self.command_char = self.peripheral.getCharacteristics(uuid = BT_Adapter.config['Dimmer_Command_buffer_UUID'])[0]
                self.brightness_level_char = self.peripheral.getCharacteristics(uuid = BT_Adapter.config['Brightness_Level_UUID'])[0]
                print self.command_char.__str__()
                command_props = self.command_char.propertiesToString()
                print command_props              
                setup_data = b"\x01\x00"
                command_char_config = self.command_char.getHandle()+1
                self.peripheral.writeCharacteristic(command_char_config, setup_data, withResponse=True)
                self.peripheral.delegate.handleNotification = self.ble_notification_handle
                retry = 0
            except BTLEException as e:
                print 'Enable notification exception %s\n' % e               
                if e.code == 1:
                    ret = self.reconnect_peripheral()
                    if ret == -1:
                        self.light_device.set_state('Disconnected')
                        self.disconnect_count = self.disconnect_count+1
                        return
                        #self.light_device.send_device_data()
                    else:
                        retry = retry-1;
        
        self.thread_handle = threading.Thread(target = self.Wait_for_notification_thread, args=[])
        self.thread_handle.start()
        
    def stop_notification_thread(self):        
        self.thread_enable = False
        self.thread_handle.join()
        print 'Thread joined'
        
    def send_device_status_to_cloud(self, state):
        self.light_device.device_state = state   
        self.light_device.send_device_data()    
                
    def send_gateway_state(self, state):
        global gatewayCommandList
        if state is 'Busy':
            print 'Sending Busy state'
            self.send_command(gatewayCommandList['gatewayBusy'])
        elif state is 'Ready':
            print 'Sending Ready state'
            self.send_command(gatewayCommandList['gatewayReady'])
        
    def scan_for_light_devices(self):
        global gatewayCommandList
        self.send_command(gatewayCommandList['getDeviceList'])   
            
    '''def scan_for_light_devices2(self, mask):
        self.recv_addr_mask = mask
        temp_device_id_list = self.extract_device_ids()
        self.update_device_list(temp_device_id_list)'''
    
    def extract_device_ids(self):
        temp_device_id_list = []
        mask = (int(binascii.b2a_hex(self.recv_brightness_level),16))
        for x in range(0,64):
            bit_check = (1<<x)&(mask)
            if bit_check > 0:
                temp_device_id_list.append(x)
        print temp_device_id_list
        return temp_device_id_list
    
    def update_device_list(self):
        print 'Updating Light device list'
        temp_device_id_list = self.extract_device_ids()
        print 'Temporary device list', temp_device_id_list
        for temp_id in temp_device_id_list:
            found = False
            for device_node in self.device_list:
                if temp_id == device_node.DALI_device_id:
                    print 'Device already exists'
                    found = True
                    break
            if found == False:
                light_dev = Light_device(temp_id, self.Gateway_MAC, self.MAC)
                self.device_list.append(light_dev)
                        
    def Wait_for_notification_thread(self):
        self.thread_enable = True
        print 'Starting new thread'
        while self.thread_enable:
            with self.lock:
                #print 'Lock acquired by thread'
                try:
                    if self.peripheral.waitForNotifications(1.0):
                        continue                     
                except BTLEException as e:
                    print 'Thread exception: %s\n' % e
                    print 'Error code: ', e.code
                    if e.code == 1:
                        ret = self.reconnect_and_subscribe_peripheral()
                        if ret == -1:
                            self.light_device.set_state('Disconnected')
                            self.disconnect_count = self.disconnect_count+1
                            self.light_device.send_device_data()
                            self.thread_enable = False            
                except MaxRetryError as e:
                    print 'RetryException: ', e   
                except:
                    print 'Unknown Error'         
            self.check_device_actions()  
            #print "Waiting..." 
            time.sleep(0.01)
               
        print 'Exit thread'
        '''try:
            while True:
                if self.peripheral.waitForNotifications(1.0):
                    continue     
                #self.check_device_actions()  
                print "Waiting..."
        except Exception:
            import traceback
            print 'Thread Exception ', traceback.format_exc() '''
        
    def try_reconnect(self, error_code):
        if error_code == 1:
            ret = self.reconnect_peripheral()
            if ret == -1:
                self.light_device.set_state('Disconnected')
                self.disconnect_count = self.disconnect_count+1
                self.light_device.send_device_data()
                return -1
        return 0
        
        
    def reconnect_peripheral(self):
        try:
            self.peripheral.connect(self.MAC)
            print 'Reconnected'
            return 0
        except BTLEException as e:
            print 'Reconnect exception: %s\n' % e
            return -1
        
    def reconnect_and_subscribe_peripheral(self):
        try:
            self.peripheral.connect(self.MAC)
            setup_data = b"\x01\x00"
            command_char_config = self.command_char.getHandle()+1
            self.peripheral.writeCharacteristic(command_char_config, setup_data, withResponse=True)
            print 'Reconnected'
            return 0
        except BTLEException as e:
            print 'Reconnect exception: %s\n' % e
            return -1
            
    def test_thread(self):
        import time
        while True:
            self.check_device_actions()
            time.sleep(1)           
    
    def check_device_actions(self):
        global gatewayCommandList
        new_action = self.test_device.get_new_action()
#       new_brightness = self.light_device.get_new_brightness()
        if new_action is not None:
            print 'Device action %s received on device %s' % (new_action,self.light_device.combined_device_id)
            if new_action == 'setOn':
                self.send_command(gatewayCommandList['turnDeviceOn'])
            elif new_action == 'setOff':
                self.send_command(gatewayCommandList['turnDeviceOff'])
#           elif new_action == 'setBrightnessLevel':
#               self.send_command(gatewayCommandList['setBrightness'], new_brightness)
#           elif new_action == 'getBrightnessLevel':
#               self.send_command(gatewayCommandList['getBrightness'])
            
#           self.light_device.new_action = None
        
    def send_command(self, command, brightness=None):        
        print 'Enter send command'
        with self.lock:
            print 'Lock acquired by send command'
            try:
                print 'Sending command', ord(command)
                self.command_char.write(command, withResponse=True)
                if brightness is not None:
                    #print 'Sending brightness level', ord(brightness)
                    print 'Sending brightness level', brightness
                    self.brightness_level_char.write(chr(brightness), withResponse=True)
                    #self.address_mask_char.write("\x00\x00\x00\x00\x00\x00\x00\x01", withResponse=False)
            except BTLEException as e:
                print('Send command Exception: %s\n' % e)
                if e.code == 1:
                    self.light_device.set_state('Disconnected')
                    self.disconnect_count = self.disconnect_count+1
                    self.light_device.send_device_data()
        print 'Exit send command'
            
    def update_artik_cloud(self):
        global gatewayCommandList
        if self.light_device.cloud_device_id is None:
            if self.light_device.add_device_to_cloud() == 0:
                self.light_device.create_device_token()
                self.light_device.send_device_data()
                self.light_device.subscribe_actions()  
        else:
            if self.light_device.device_token is None:
                self.light_device.create_device_token()
            if self.light_device.subscription_state is 'Disconnected':
                self.light_device.subscribe_actions()  
        
                         
        return 

    def get_device_state(self):
        self.send_command(gatewayCommandList['getDeviceStatus']) 
    
    def __del__(self):
        print 'Destroying Adapter object with MAC', self.MAC