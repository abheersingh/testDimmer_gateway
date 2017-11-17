import Test_Bluetooth_Adapters
import Light_devices
from Test_Bluetooth_Adapters import BT_Adapter
from Light_devices import Light_device
from threading import Timer
import time
from bluepy.btle import Scanner, UUID, Peripheral, DefaultDelegate, BTLEException

class gateway:
    GATEWAY_MAC = []
    config = []    
    Gateway_state = None
    def __init__(self):
        self.Adapter_list = []
        self.initialize_system()
        gateway.Gateway_state = 'Busy'
        temp_Adapter_list = self.scan_and_connect()
        self.update_local_database(temp_Adapter_list)                
        self.update_artik_database()   
        
    def initialize_system(self):         
        print 'Initializing...'
        Light_devices.initialize_cloud()
        gateway.GATEWAY_MAC = Bluetooth_Adapters.initialize_bluetooth()
        print gateway.GATEWAY_MAC
        return
    
    def scan_and_connect(self):
        print 'Scanning for BLE devices'
        temp_Adapter_list = []
        scanner = Scanner()
        try:
            devices = scanner.scan(10)  # Perform a 10 seconds BLE scan
        except BTLEException as e:
            print('Exception: %s\n' % e)
            print 'Error code: ', e.code
        for dev in devices:
            print "Device %s (%s), RSSI=%d dB" % (dev.addr.upper(), dev.addrType, dev.rssi)
            dev.addr = dev.addr.upper()
            for (adtype, desc, value) in dev.getScanData():
                print "  %s = %s" % (desc, value)
                if desc == 'Complete Local Name' and value == 'Dimmer Adapter':
                    print "  %s = %s" % (desc, value)
                    try:
                        dev_conn = BT_Adapter(dev.addr, gateway.GATEWAY_MAC)
                        dev_svc=dev_conn.peripheral.getServiceByUUID(ssssAdapter.config['Dimmer_Service_UUID'])
                        print "Service:"                
                        print(dev_svc)
                        print dev_conn  
                        #self.getCharacs(dev_svc)
                        temp_Adapter_list.append(dev_conn)
                                       
                    except BTLEException as e:
                        print('Exception: %s\n' % e)
                        print 'Error code: ', e.code
           
        print temp_Adapter_list
        return temp_Adapter_list          
       
    def update_local_database(self, temp_DALI_adapter_list):
        print 'Updating local database'
        self.update_adapter_list(temp_DALI_adapter_list)
        self.print_Adapter_list()
        #self.update_device_list()
            
    def update_adapter_list(self, temp_DALI_adapter_list):
        
        print "Bluetooth_Adapters list found: %s\n" % temp_DALI_adapter_list
        for adapter_node in temp_DALI_adapter_list:
            found = False
            print "Bluetooth_Adapters node: %s\n" % adapter_node.MAC
            for registered_adapter in self.Adapter_list:
                if adapter_node.MAC == registered_adapter.MAC:
                    # For existing but disconnected devices, restart the notification thread
                    found = True
                    print 'found'
                    registered_adapter.peripheral = adapter_node.peripheral
                    registered_adapter.stop_notification_thread()
                    registered_adapter.enable_notification()
                    break
                 
            if found == False:
                print 'Not found'
                adapter_node.enable_notification()
                self.Adapter_list.append(adapter_node)
                adapter_node.send_gateway_state(gateway.Gateway_state)
                
        return
    
    def send_state_to_adapters(self):
        for adapter_node in self.Adapter_list:
            adapter_node.send_gateway_state(gateway.Gateway_state)
            
    def update_device_list(self):
        print 'Sending commands to all the adapters to get complete device list'
        for adapter_node in self.Adapter_list:
            adapter_node.scan_for_light_devices()
        '''import random
        for adapter_node in self.Adapter_list:
            random_num = random.randint(0,10) 
            print 'Random number', random_num
            adapter_node.scan_for_light_devices2(random_num)'''
            
    def update_artik_database(self):
        for adapter_node in self.Adapter_list:
            adapter_node.update_artik_cloud()
            
    def update_device_status(self):
        for adapter_node in self.Adapter_list:
            adapter_node.get_device_state()
            
    def display_disconnect_count(self):
        for adapter_node in self.Adapter_list:
            print '%s has disconnected %d times' %(adapter_node.MAC, adapter_node.disconnect_count)
            
    def Ready(self):        
        while True:
            gateway.Gateway_state = 'Ready'
            print 'Gateway state ', gateway.Gateway_state
            self.send_state_to_adapters()
            self.update_device_status()
            time.sleep(60)
            print 'Periodic scan and update'
            gateway.Gateway_state = 'Busy'
            print 'Gateway state ', gateway.Gateway_state
            self.send_state_to_adapters()
            temp_Adapter_list = self.scan_and_connect()
            self.update_local_database(temp_Adapter_list)
            self.update_artik_database()  
            self.display_disconnect_count()            
           
    def print_Adapter_list(self):
        print 'Adapter List:'
        for adapter_node in self.Adapter_list:
            print adapter_node.MAC
            
    def __del__(self):
        print 'Deleting Adapter list'
        '''for adapter in self.Adapter_list:
            del adapter'''        
        #del self.Adapter_list[:]
        for i in range(0,len(self.Adapter_list)):
            del self.Adapter_list[i]
            

if __name__ == '__main__':
    gateway_obj = gateway()
    print 'Entering Ready state'
    gateway_obj.Ready()
    #print 'Deleting gateway'
    #del gateway_obj
    
    while True:
        pass
    '''
f000aa41-0451-4000-b000-000000000000
f000aa42-0451-4000-b000-000000000000
f000aa44-0451-4000-b000-000000000000'''