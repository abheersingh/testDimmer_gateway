import time

class Test_device:

	def __init__(self):
		self.new_action = None

	def set_new_action(self):
		while True:
			self.new_action = 'setOn'
			time.sleep(15)
			self.new_action = 'setOff'

	def get_new_action(self):
        return self.new_action