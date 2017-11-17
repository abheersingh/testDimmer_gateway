import time, json
import artikcloud
import threading
from artikcloud.rest import ApiException
from pprint import pprint
import requests
from urllib3.exceptions import MaxRetryError
from requests.exceptions import ConnectionError

import certifi
import paho.mqtt.client as mqtt

def initialize_cloud():
    with open("config.json", 'r') as config_file:
        Light_device.config = json.load(config_file)['ArtikCloud']    
        #print Light_device.config
    try:
        with open('cloud_device_list.txt', 'r') as device_file:
            Light_device.device_list = json.load(device_file)
            #print Light_device.device_list
    except:
        return
    return

class Light_device:
    config = []
    device_list = {}
    def __init__(self, device_id, Gateway_MAC, adapter_MAC):
        self.cloud_device_id = None
        self.DALI_device_id = device_id
        self.Gateway_MAC = Gateway_MAC
        self.adapter_MAC = adapter_MAC
        self.combined_device_id = self.Gateway_MAC + '.' + self.adapter_MAC + '.' + str(self.DALI_device_id)
        self.device_token = None
        self.device_state = 'OFF'
        self.subscription_state='Disconnected'
        self.brightness_level = 0
        self.new_brightness_level = None
        self.mqtt_client = None
        self.publish_channel = None
        self.actions_channel = None
        self.new_action = None
        print 'Combined device ID', self.combined_device_id
        
    def check_device_presence_on_cloud(self):
        # Configure OAuth2 access token for authorization: artikcloud_oauth
        artikcloud.configuration.access_token = Light_device.config['AuthToken']
        
        if self.combined_device_id in Light_device.device_list:
            # create an instance of the API class
            api_instance = artikcloud.DevicesApi()
            device_id = Light_device.device_list[self.combined_device_id] # str | Device ID.
            
            try: 
                # Get device presence information
                api_response = api_instance.get_device_presence(device_id)
                pprint(api_response)
                self.cloud_device_id = Light_device.device_list[self.combined_device_id]
                print 'Device already exists on cloud'
                return 1
            except ApiException as e:
                print("Exception when calling DevicesApi->get_device_presence: %s\n" % e)
                del Light_device.device_list[self.combined_device_id]
                return 0
            except MaxRetryError as e:
                print 'Connection Error'
                return -1
        else:
            return 0
        
    def add_device_to_cloud(self):
        
        device_already_exists = self.check_device_presence_on_cloud()
        
        if device_already_exists == 0:
            # Configure OAuth2 access token for authorization: artikcloud_oauth
            artikcloud.configuration.access_token = Light_device.config['AuthToken']
            
            # create an instance of the API class
            api_instance = artikcloud.DevicesApi()
            device = artikcloud.Device(uid = Light_device.config['userID'], dtid = Light_device.config['deviceTypeID'], name = "Dimmer", manifest_version_policy = "LATEST") # Device | Device to be added to the user
            
            try: 
                # Add Device
                api_response = api_instance.add_device(device)
                device_dict = api_response.to_dict()
                self.cloud_device_id = device_dict['data']['id']
                Light_device.device_list[self.combined_device_id] = self.cloud_device_id
                with open('cloud_device_list.txt', 'w') as device_file:
                    device_file.write(json.dumps(Light_device.device_list))
            except ApiException as e:
                print("Exception when calling DevicesApi->add_device: %s\n" % e)
                return -1
            except MaxRetryError as e:
                print 'Connection Error'
                return -1
        elif device_already_exists == -1:
            return -1
        return 0
    
            
    def create_device_token(self):
        print 'Creating device token'
        #time.sleep(5)
        payload = {
            "Content-Type": "application/json",
            "Authorization": 'Bearer '+ Light_device.config['AuthToken']
        }
        endpoint = "https://api.artik.cloud/v1.1/devices/" + self.cloud_device_id +"/tokens"
        try:
            r = requests.put(endpoint, data=payload)
        except:
            print 'Failed to create device token'
            return
        result = json.loads(r.content)
        #print r.content
        #print result['data']['accessToken']
        self.device_token = result['data']['accessToken']
        
    def send_device_data(self):
        # Configure Oauth2 access_token for the client application.  Here we have used
        # the device token for the configuration
        artikcloud.configuration = artikcloud.Configuration();
        
        # We create an instance of the Message API class which provides
        # the send_message() and get_last_normalized_messages() api call
        # for our example
        api_instance = artikcloud.MessagesApi()
        if self.device_token is not None:
            artikcloud.configuration.access_token = self.device_token
        else:
            print 'Error sending data to cloud: No device token'
            return
                    
        # set your custom timestamp
        ts = None
        device_message = {}
        device_message["id"] = self.combined_device_id
        device_message["state"] = self.device_state
        print 'Device state is ', self.device_state
        device_message["adapterMAC"] = self.adapter_MAC
        device_message["brightnessLevel"] = self.brightness_level
        # Construct a Message object for your request
        data = artikcloud.Message(device_message, self.cloud_device_id, ts) 
        
        try:         
            # Send Message
            print data
            api_response = api_instance.send_message(data)
            pprint(api_response)
        except ApiException as e:
            pprint("Exception when calling MessagesApi->send_message: %s\n" % e)
        except MaxRetryError as e:
            print 'Connection Error' 
        print 'Returning'
        return
    
    def get_new_action(self):
        return self.new_action
    
    def get_new_brightness(self):
        return self.new_brightness_level
    
    def set_state(self, new_state):
        self.device_state = new_state
    
    def set_brightness(self, new_brightness):
        self.brightness_level=new_brightness
    
    def subscribe_actions(self):
        try:
            self.publish_channel = "/v1.1/messages/{}".format(self.cloud_device_id)
            self.actions_channel = "/v1.1/actions/{}".format(self.cloud_device_id)
            self.mqtt_client = mqtt.Client(self.combined_device_id)
            self.mqtt_client.on_connect = self.on_connect
            self.mqtt_client.on_disconnect = self.on_disconnect
            self.mqtt_client.on_message = self.on_message
            self.mqtt_client.on_log = self.on_log
            print("Connecting!")
            self.mqtt_client.username_pw_set(self.cloud_device_id, password=self.device_token)
            self.mqtt_client.tls_set(certifi.where())
            self.mqtt_client.connect(Light_device.config['ARTIK_MQTT_URL'], Light_device.config['ARTIK_MQTT_PORT'], keepalive=60)
        except:
            print 'Connection Error'
            return
        self.subscription_state='Connected'
        self.mqtt_client.loop_start()
        '''while True:
            time.sleep(1)'''
        return
    
    def on_connect(self, client, userdata, flags, rc):
        """The callback for when the client receives a CONNACK response from the server
        """
        print("Connected with result code "+str(rc))
        print userdata
        # If connected cleanly
        if rc == 0:
            # Subscribing in on_connect() means that if we lose the connection and
            # reconnect then subscriptions will be renewed.
            client.subscribe(self.actions_channel)
            # Start readings
    
    def on_disconnect(self, client, userdata, rc):
        """Callback for when the client receives disconnects from the server.
        """
        print("Disconnected with result code "+str(rc))
        self.subscription_state='Disconnected'
        client.loop_stop(True)
    
    def on_message(self, client, userdata, msg):
        """Callback for when a PUBLISH message is received from the server
        """
        #print 'Message', msg
        #print(msg.topic+" "+str(msg.payload))
        try:
            data = json.loads(msg.payload)
            #print 'Data', data
        except json.decoder.JSONDecodeError:
            print("Can't decode payload: {}".format(msg.payload))
        else:
            if "actions" in data:
                self.handle_actions(data['actions'])
    
    def on_log(self, client, userdata, level, buf):
        """Callback on logging event, printing to the device log stream
        """
        print(buf)
    def handle_actions(self, actions):
        """Handling incoming actions
        """
        simple_actions = ['setOn', 'setOff', 'getBrightnessLevel']
        for action in actions:
            '''if action['name'] == 'setOn':
                print action['name']
                self.new_action = action['name']
                #common.action_set_text(action['parameters']['text'])
            elif action['name'] == 'setOff':
                print action['name']
                self.new_action = action['name']
                #common.action_set_off()'''
            if action['name'] in simple_actions:
                print action['name']
                self.new_action = action['name']
            elif action['name'] == 'setBrightnessLevel':
                print action['name']
                print action['parameters']['level']
                self.new_action = action['name']
                self.new_brightness_level = action['parameters']['level']
            else:
                print("Unknown action: {}".format(action['name']))
                print action
        
    
