from asyncio.tasks import sleep
from json.decoder import JSONDecodeError
import threading
import errno
import select
import socket
import json
import requests
from requests.exceptions import ConnectionError
import atexit
import time
import asyncio
import datetime
import os

class xyze_t:
	x = 0.0
	y = 0.0
	z = 0.0
	e = 0.0
	home_x = False
	home_y = False
	home_z = False
	updated = False

class AxisEnum:
	X_AXIS = 0
	A_AXIS = 0
	Y_AXIS = 1
	B_AXIS = 1
	Z_AXIS = 2
	C_AXIS = 2
	E_AXIS = 3
	X_HEAD = 4
	Y_HEAD = 5
	Z_HEAD = 6
	E0_AXIS = 3
	E1_AXIS = 4
	E2_AXIS = 5
	E3_AXIS = 6
	E4_AXIS = 7
	E5_AXIS = 8
	E6_AXIS = 9
	E7_AXIS = 10
	ALL_AXES = 0xFE
	NO_AXIS = 0xFF

class HMI_value_t:
	E_Temp = 0
	Bed_Temp = 0
	Fan_speed = 0
	print_speed = 100
	Max_Feedspeed = 0.0
	Max_Acceleration = 0.0
	Max_Jerk = 0.0
	Max_Step = 0.0
	Move_X_scale = 0.0
	Move_Y_scale = 0.0
	Move_Z_scale = 0.0
	Move_E_scale = 0.0
	offset_value = 0.0
	show_mode = 0  # -1: Temperature control    0: Printing temperature

class HMI_Flag_t:
	language = 0
	pause_flag = False
	pause_action = False
	print_finish = False
	done_confirm_flag = False
	select_flag = False
	home_flag = False
	heat_flag = False  # 0: heating done  1: during heating
	ETempTooLow_flag = False
	leveling_offset_flag = False
	feedspeed_axis = AxisEnum()
	acc_axis = AxisEnum()
	jerk_axis = AxisEnum()
	step_axis = AxisEnum()

class buzz_t:
	def tone(self, t, n):
		pass

class material_preset_t:
	def __init__(self, name, hotend_temp, bed_temp, fan_speed=100):
		self.name = name
		self.hotend_temp = hotend_temp
		self.bed_temp = bed_temp
		self.fan_speed = fan_speed

class KlippySocket:
	def __init__(self, uds_filename, callback=None, debug=False):
		self.Debug = debug
		self.connected = False
		self.webhook_socket_create(uds_filename)
		self.lock = threading.Lock()
		self.poll = select.poll()
		self.stop_threads = False
		self.poll.register(self.webhook_socket, select.POLLIN | select.POLLHUP)
		self.socket_data = ""
		self.t = threading.Thread(target=self.polling)
		self.callback = callback
		self.lines = []
		self.t.start()
		atexit.register(self.klippyExit)

	def klippyExit(self):
		print("Closing Klippy Socket")
		self.stop_threads = True
		self.t.join()

	def webhook_socket_create(self, uds_filename):
		self.webhook_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.webhook_socket.setblocking(0)
		print("Waiting for connection: %s\n" % (uds_filename,))
		while 1:
			try:
				self.webhook_socket.connect(uds_filename)
			except socket.error as e:
				if e.errno == errno.ECONNREFUSED:
					time.sleep(0.1)
					continue
				print(
					"Unable to connect socket %s [%d,%s]\n" % (
						uds_filename, e.errno,
						errno.errorcode[e.errno]
					))
				exit(-1)
			break
		print("Connected.\n")
		self.connected = True

	def process_socket(self):
		data = None
		try:
			data = self.webhook_socket.recv(4096).decode()
		except:
			pass
		if not data:
			self.connected = False
			print("Socket closed\n")
			exit(-1)
		parts = data.split('\x03')
		parts[0] = self.socket_data + parts[0]
		self.socket_data = parts.pop()
		for line in parts:
			if self.callback:
				self.callback(line)

	def queue_line(self, line):
		with self.lock:
			self.lines.append(line)

	def send_line(self):
		if len(self.lines) == 0:
			return
		line = self.lines.pop(0).strip()
		if not line or line.startswith('#'):
			return
		try:
			m = json.loads(line)
		except JSONDecodeError:
			print("ERROR: Unable to parse line\n")
			return
		cm = json.dumps(m, separators=(',', ':'))
		wdm = '{}\x03'.format(cm)
		self.webhook_socket.send(wdm.encode())

	def polling(self):
		while True:
			if self.stop_threads:
				break
			res = self.poll.poll(1000.)
			for fd, event in res:
				self.process_socket()
			with self.lock:
				self.send_line()


class MoonrakerSocket:
	def __init__(self, address, port, api_key):
		self.s = requests.Session()
		self.s.headers.update({
			'X-Api-Key': api_key,
			'Content-Type': 'application/json'
		})
		self.base_address = 'http://' + address + ':' + str(port)


class PrinterData:
	event_loop = None
	HAS_HOTEND = True
	HOTENDS = 1
	HAS_HEATED_BED = True
	HAS_FAN = True #False
	HAS_ZOFFSET_ITEM = True
	HAS_ONESTEP_LEVELING = True #False
	HAS_PREHEAT = True
	HAS_BED_PROBE = False
	PREVENT_COLD_EXTRUSION = True
	EXTRUDE_MINTEMP = 170
	EXTRUDE_MAXLENGTH = 200

	HEATER_0_MAXTEMP = 330
	HEATER_0_MINTEMP = 5
	HOTEND_OVERSHOOT = 15

	MAX_E_TEMP = (HEATER_0_MAXTEMP - (HOTEND_OVERSHOOT))
	MIN_E_TEMP = HEATER_0_MINTEMP

	BED_OVERSHOOT = 10
	BED_MAXTEMP = 150
	BED_MINTEMP = 5

	BED_MAX_TARGET = (BED_MAXTEMP - (BED_OVERSHOOT))
	MIN_BED_TEMP = BED_MINTEMP

	X_MIN_POS = 0.0
	Y_MIN_POS = 0.0
	Z_MIN_POS = 0.0
	Z_MAX_POS = 260

	Z_PROBE_OFFSET_RANGE_MIN = -20
	Z_PROBE_OFFSET_RANGE_MAX = 20

	buzzer = buzz_t()

	material_preset = [
		material_preset_t('PLA', 200, 60),
		material_preset_t('ABS', 210, 100),
		material_preset_t('TPU', 210, 100)
	]
	files = None
	MACHINE_SIZE = "240x240x260"
	SHORT_BUILD_VERSION = "1.00"
	CORP_WEBSITE_E = "https://www.klipper3d.org/"

	def __init__(self, API_Key, URL='127.0.0.1', klippy_sock='/home/biqu/printer_data/comms/klippy.sock', callback=None, debug=False):
		self.Debug = debug
		self.response_callback = callback
		self.klippy_sock      = klippy_sock
		self.BABY_Z_VAR       = 0
		self.print_speed      = 100
		self.flow_percentage  = 100
		self.led_percentage   = 0
		self.temphot          = 0
		self.tempbed          = 0
		self.HMI_ValueStruct  = HMI_value_t()
		self.HMI_flag         = HMI_Flag_t()
		self.current_position = xyze_t()
		self.gcm              = None
		self.z_offset         = 0
		self.thermalManager   = {
			'temp_bed': {'celsius': 20, 'target': 120},
			'temp_hotend': [{'celsius': 20, 'target': 120}],
			'fan_speed': [100]
		}
		self.job_Info               = None
		self.file_path              = None
		self.file_name              = None
		self.status                 = None
		self.max_velocity           = None
		self.max_accel              = None
		self.minimum_cruise_ratio     = None
		self.square_corner_velocity = None
		
		self.op = MoonrakerSocket(URL, 80, API_Key)
		print(self.op.base_address)

		self.klippy_start()

		self.event_loop = asyncio.new_event_loop()
		threading.Thread(target=self.event_loop.run_forever, daemon=True).start()

	# ------------- Klipper Function ----------
	def klippy_start(self):
		self.ks = KlippySocket(self.klippy_sock, callback=self.klippy_callback, debug=self.Debug)
		subscribe = {
			"id": 4001,
			"method": "objects/subscribe",
			"params": {
				"objects": {
					"toolhead": [
						"position"
					]
				},
				"response_template": {}
			}
		}
		self.klippy_z_offset = '{"id": 4002, "method": "objects/query", "params": {"objects": {"configfile": ["config"]}}}'
		self.klippy_home = '{"id": 4003, "method": "objects/query", "params": {"objects": {"toolhead": ["homed_axes"]}}}'
		self.gcode = '{"id": 4004, "method": "gcode/subscribe_output", "params": {"response_template":{}}}'

		self.ks.queue_line(json.dumps(subscribe))
		self.ks.queue_line(self.klippy_z_offset)
		self.ks.queue_line(self.klippy_home)
		self.ks.queue_line(self.gcode)

	def klippy_callback(self, line):
		klippyData = json.loads(line)
		if self.Debug:
			print("klippy_callback:")
			print(json.dumps(klippyData, indent=2))
		status = None
		if 'result' in klippyData:
			if 'status' in klippyData['result']:
				status = klippyData['result']['status']
		if 'params' in klippyData:
			if 'status' in klippyData['params']:
				status = klippyData['params']['status']
			if 'response' in klippyData['params']:
				if self.response_callback:
					resp = klippyData['params']['response']
					if 'B:' in resp and 'T0:' in resp:
						pass ## Filter out temperature responses
					else:
						self.response_callback(resp, 'response')

		if status:
			if 'toolhead' in status:
				if 'position' in status['toolhead']:
					if self.current_position.x != status['toolhead']['position'][0]:
						self.current_position.x = status['toolhead']['position'][0]
						self.current_position.updated = True
					if self.current_position.y != status['toolhead']['position'][1]:
						self.current_position.y = status['toolhead']['position'][1]
						self.current_position.updated = True
					if self.current_position.z != status['toolhead']['position'][2]:
						self.current_position.z = status['toolhead']['position'][2]
						self.current_position.updated = True
					if self.current_position.e != status['toolhead']['position'][3]:
						self.current_position.e = status['toolhead']['position'][3]
						self.current_position.updated = True
					
				if 'homed_axes' in status['toolhead']:
					if 'x' in status['toolhead']['homed_axes']:
						self.current_position.home_x = True
					else:
						self.current_position.home_x = False
					if 'y' in status['toolhead']['homed_axes']:
						self.current_position.home_y = True
					else:
						self.current_position.home_y = False
					if 'z' in status['toolhead']['homed_axes']:
						self.current_position.home_z = True
					else:
						self.current_position.home_z = False
				
				if 'max_velocity' in status['toolhead']:
					if self.max_velocity != status['toolhead']['max_velocity']:
						self.max_velocity = status['toolhead']['max_velocity']
				if 'max_accel' in status['toolhead']:
					if self.max_accel != status['toolhead']['max_accel']:
						self.max_accel = status['toolhead']['max_accel']
				if 'minimum_cruise_ratio' in status['toolhead']:
					if self.minimum_cruise_ratio != status['toolhead']['minimum_cruise_ratio']:
						self.minimum_cruise_ratio = status['toolhead']['minimum_cruise_ratio']
				if 'square_corner_velocity' in status['toolhead']:
					if self.square_corner_velocity != status['toolhead']['square_corner_velocity']:
						self.square_corner_velocity = status['toolhead']['square_corner_velocity']

			if 'configfile' in status:
				if 'config' in status['configfile']:
					if 'bltouch' in status['configfile']['config']:
						if 'z_offset' in status['configfile']['config']['bltouch']:
							if status['configfile']['config']['bltouch']['z_offset']:
								self.BABY_Z_VAR = float(status['configfile']['config']['bltouch']['z_offset'])
					if 'virtual_sdcard' in status['configfile']['config']:
						if 'path' in status['configfile']['config']['virtual_sdcard']:
							self.file_path = status['configfile']['config']['virtual_sdcard']['path']

	def ishomed(self):
		self.update_variable()
		condition_1 = False
		condition_2 = False
		if self.current_position.home_x and self.current_position.home_y and self.current_position.home_z:
			condition_1 = True
   
		if 'position' in self.toolhead:
				self.current_position.x = self.toolhead['position'][0]
				self.current_position.y = self.toolhead['position'][1]
				self.current_position.z = self.toolhead['position'][2]
				self.current_position.e = self.toolhead['position'][3]
		
		if self.current_position.x != 0 or self.current_position.y != 0:
			condition_2 = True
		
		if (condition_1 and condition_2):
			return True
		else:
			self.ks.queue_line(self.klippy_home)
			return False

	def offset_z(self, new_offset):
		self.BABY_Z_VAR = new_offset
		self.sendGCode('ACCEPT')

	def add_mm(self, axs, new_offset):
		gc = 'TESTZ Z={}'.format(new_offset)
		print(axs, gc)
		self.sendGCode(gc)
	
	def probe_adjust(self, change):
		gc = 'TESTZ Z={}'.format(change)
		print(gc)
		self.sendGCode(gc)

	
	# ------------- OctoPrint Function ----------

	def getREST(self, path):
		r = self.op.s.get(self.op.base_address + path)
		d = r.content.decode('utf-8')
		try:
			return json.loads(d)
		except JSONDecodeError:
			print('Decoding JSON has failed')
		return None

	async def _postREST(self, path, json):
		self.op.s.post(self.op.base_address + path, json=json)

	def postREST(self, path, json):
		self.event_loop.call_soon_threadsafe(asyncio.create_task,self._postREST(path,json))

	def init_Webservices(self):
		try:
			requests.get(self.op.base_address)
		except ConnectionError:
			print('Web site does not exist')
			return
		else:
			print('Web site exists')
		if self.getREST('/api/printer') is None:
			return
		self.update_variable()

		#alternative approach
		#full_version = self.getREST('/printer/info')['result']['software_version']
		#self.SHORT_BUILD_VERSION = '-'.join(full_version.split('-',2)[:2])
		self.SHORT_BUILD_VERSION = self.getREST('/machine/update/status?refresh=false')['result']['version_info']['klipper']['version']

		data = self.getREST('/printer/objects/query?toolhead')['result']['status']
		#print(json.dumps(data, indent=2))
		toolhead = data['toolhead']
		volume = toolhead['axis_maximum'] #[x,y,z,w]
		self.MACHINE_SIZE = "{}x{}x{}".format(
			int(volume[0]),
			int(volume[1]),
			int(volume[2])
		)
		self.X_MAX_POS = int(volume[0])
		self.Y_MAX_POS = int(volume[1])
		self.max_velocity = toolhead.get('max_velocity', 0.0) # Use a default value if the key is not present
		self.max_accel = toolhead.get('max_accel', 0.0) # Use a default value if the key is not present
		self.minimum_cruise_ratio = toolhead.get('minimum_cruise_ratio', 0.0) # Use a default value if the key is not present
		self.square_corner_velocity = toolhead.get('square_corner_velocity', 0.0) # Use a default value if the key is not present

	def get_gcode_store(self, count=100):
	# 	gcode_example = '''[
    #   {'message': 'M190 S60', 'time': 1736975306.9046052, 'type': 'command'}, 
    #   {'message': 'M109 S150', 'time': 1736975306.9411252, 'type': 'command'}
    #   ]'''
		gcode_store = None
		try:
			gcode_store = self.getREST('/server/gcode_store?count=%d' % count)['result']['gcode_store']
		except:
			print("GCode store read failed!")
		return gcode_store

	def wait_for_gcode_command(self,gcode_code,start_code='CODE_START',count=2, interval=1):
		print(f"Waiting for {gcode_code} command...")
		#DEBUG
		current_time = datetime.datetime.now() - datetime.timedelta(seconds=1)		
		while True:
			time.sleep(interval)
			gcode_store = self.get_gcode_store(count=count)
			if not gcode_store:
				continue
			for entry in gcode_store:
				entry_time = datetime.datetime.fromtimestamp(entry['time'])
				if (entry_time < current_time):
					continue
				entry_str = str(entry['message'])					
				if 'SAVE_CONFIG' in entry_str:
					print(f"SAVE_CONFIG command detected!")
					return
				if 'CODE_END' in entry_str :
					print(f"CODE_END command detected!")
					return
				if gcode_code in entry_str:
					print(f"{gcode_code} command detected!")
					return




	def wait_for_standby(self, interval=1):
		print(f"Waiting for Stanby...")
		while True:
			time.sleep(interval)
			state = self.getState()
			if state == 'standby':
				return 

	def get_macros(self, filter_internal = True):
		macros = []
		try:
			objects = self.getREST('/printer/objects/list')['result']['objects']
		except:
			print("Could not read macro objects!")
		
		for obj in objects:
			if 'gcode_macro' in obj:
				macro = obj.split(' ')[1]
				if filter_internal:
					if macro[0] != '_':
						macros.append(macro)
				else:
					macros.append(macro)
		return macros	

	def list_files(self,directory):	
		file_paths = []
		if not os.path.exists(directory):
			return file_paths
		for file in os.listdir(directory):
			if not self.files:
				self.files = []
			path = os.path.join(directory, file)
			file_paths.append(path)
			self.files.append({'path': path})
		return file_paths

	def GetFiles(self, refresh=False):
		names = []		
		if not self.files or refresh:
			try:
				sd_card_path = "~/gcode_files/sda1" 
				sd_card_path = os.path.expanduser(sd_card_path)
				self.files = self.getREST(f'/server/files/list?path={sd_card_path}')["result"]
				if self.files is None or len(self.files) == 0:
					self.files = self.getREST('/server/files/list')["result"]
			except Exception as ex:
				print(f"Exception 418\n {ex}")
		
		for fl in self.files:
			names.append(fl["path"])
		return names


	def update_variable(self):
		if self.ks.connected == False:
			self.ks.klippyExit()
			self.klippy_start()
			return False
		query = '/printer/objects/query?extruder&heater_bed&gcode_move&fan&print_stats&motion_report&toolhead'
		try:
			data = self.getREST(query)['result']['status']
		except:
			print("Exception 431")
			return False

		#print("update_variable:")
		#print(json.dumps(data, indent=2))
		self.gcm = data['gcode_move']
		# self.z_offset = self.gcm['homing_z_offset'] #z offset
		self.z_offset = self.gcm['homing_origin'][2] #z offset
		self.flow_percentage = self.gcm['extrude_factor'] * 100 #flow rate percent
		self.absolute_moves = self.gcm['absolute_coordinates'] #absolute or relative
		self.absolute_extrude = self.gcm['absolute_extrude'] #absolute or relative
		self.speed = self.gcm['speed'] #current speed in mm/s
		self.print_speed = self.gcm['speed_factor'] * 100 #print speed percent
		self.bed = data['heater_bed'] #temperature, target
		self.extruder = data['extruder'] #temperature, target
		self.fan = data['fan']
		self.toolhead = data['toolhead']
		Update = False
		try:
			if self.thermalManager['temp_bed']['celsius'] != int(self.bed['temperature']):
				self.thermalManager['temp_bed']['celsius'] = int(self.bed['temperature'])
				Update = True
			if self.thermalManager['temp_bed']['target'] != int(self.bed['target']):
				self.thermalManager['temp_bed']['target'] = int(self.bed['target'])
				Update = True
			if self.thermalManager['temp_hotend'][0]['celsius'] != int(self.extruder['temperature']):
				self.thermalManager['temp_hotend'][0]['celsius'] = int(self.extruder['temperature'])
				Update = True
			if self.thermalManager['temp_hotend'][0]['target'] != int(self.extruder['target']):
				self.thermalManager['temp_hotend'][0]['target'] = int(self.extruder['target'])
				Update = True
			if self.thermalManager['fan_speed'][0] != int((self.fan['speed'] * 100) + 0.5):
				self.thermalManager['fan_speed'][0] = int((self.fan['speed'] * 100) + 0.5)
				Update = True
			if self.BABY_Z_VAR != self.z_offset:
				self.BABY_Z_VAR = self.z_offset
				self.HMI_ValueStruct.offset_value = self.z_offset * 100
				Update = True
			
			if self.max_velocity != self.toolhead['max_velocity']:
				self.max_velocity = self.toolhead['max_velocity']
				Update = True
			if self.max_accel != self.toolhead['max_accel']:
				self.max_accel = self.toolhead['max_accel']
				Update = True
			if self.minimum_cruise_ratio != self.toolhead['minimum_cruise_ratio']:
				self.minimum_cruise_ratio = self.toolhead['minimum_cruise_ratio']
				Update = True
			if self.square_corner_velocity != self.toolhead['square_corner_velocity']:
				self.square_corner_velocity = self.toolhead['square_corner_velocity']
				Update = True
		except Exception as ex:
			print(f"Exception 470:\n{ex}")
			pass #missing key, shouldn't happen, fixes misses on conditionals \_(?)_/
		try:
			self.job_Info = self.getREST('/printer/objects/query?virtual_sdcard&print_stats')['result']['status']
		except Exception as ex:
			print(f"Exception update_variable:\n{ex}")
			return False

		if self.job_Info:
			self.file_name = self.job_Info['print_stats']['filename']
			self.status = self.job_Info['print_stats']['state']
			self.HMI_flag.print_finish = self.getPercent() == 100.0
		return Update

	def getState(self):
		if self.job_Info:
			return self.job_Info['print_stats']['state']
		else:
			return None

	def printingIsPaused(self):
		if self.job_Info:
			return self.job_Info['print_stats']['state'] == "paused" or self.job_Info['print_stats']['state'] == "pausing"
		else:
			return None

	def getPercent(self):
		if self.job_Info:
			if self.job_Info['virtual_sdcard']['is_active']:
				return self.job_Info['virtual_sdcard']['progress'] * 100
		return 0

	def duration(self):
		if self.job_Info:
			if self.job_Info['virtual_sdcard']['is_active']:
				return self.job_Info['print_stats']['print_duration']
		return 0

	def remain(self):
		percent = self.getPercent()
		duration = self.duration()
		if percent:
			total = duration / (percent / 100)
			return total - duration
		return 0

	def openAndPrintFile(self, filenum):
		self.file_name = self.files[filenum]['path']
		self.postREST('/printer/print/start', json={'filename': self.file_name})

	def cancel_job(self): #fixed
		print('Canceling job:')
		self.postREST('/printer/print/cancel', json=None)

	def pause_job(self): #fixed
		print('Pausing job:')
		self.postREST('/printer/print/pause', json=None)

	def resume_job(self): #fixed
		print('Resuming job:')
		self.postREST('/printer/print/resume', json=None)

	def set_print_speed(self, fr):
		self.print_speed = fr
		self.sendGCode('M220 S%d' % fr)

	def set_flow(self, fl):
		self.flow_percentage = fl
		self.sendGCode('M221 S%d' % fl)

	def set_led(self, led):
		self.led_percentage = led
		if(led > 0):
			self.sendGCode('GANTRY_LIGHT_ON')
		else:
			self.sendGCode('GANTRY_LIGHT_OFF')

	def set_fan(self, fan):
		self.fan_percentage = fan
		self.sendGCode('M106 S%s' % (int)(fan*255/100))

	def home(self, axis): #fixed using gcode
		GCode = 'G28 '
		if axis == 'X' or axis == 'Y':
			GCode += axis
			GCode += f'\nG0 {axis}0 F3000'
		self.sendGCode(GCode)

	def moveRelative(self, axis:str, distance, speed):
		if axis.upper() == 'E':
			self.sendGCode('M83\n%s \n%s %s%s F%s%s' % ('G91', 'G1', axis, distance, speed,
				'\nG90' if self.absolute_moves else ''))
			return True
		if self.ishomed():
			self.sendGCode('%s \n%s %s%s F%s%s' % ('G91', 'G1', axis, distance, speed,
				'\nG90' if self.absolute_moves else ''))
			return True
		return False

	def moveAbsolute(self, axis:str, position, speed):
		if axis.upper() == 'E' or self.ishomed():
			self.sendGCode('%s \n%s %s%s F%s%s' % ('G90', 'G1', axis, position, speed,
				'\nG91' if not self.absolute_moves else ''))
			return True
		return False

	def sendGCode(self, gcode):
		self.postREST('/printer/gcode/script', json={'script': gcode})
		if self.response_callback:
			self.response_callback(gcode, 'command')

	def disable_all_heaters(self):
		self.setExtTemp(0)
		self.setBedTemp(0)

	def zero_fan_speeds(self):
		pass

	def preheat(self, profile):
		if profile == "PLA":
			self.preHeat(self.material_preset[0].bed_temp, self.material_preset[0].hotend_temp)
		elif profile == "ABS":
			self.preHeat(self.material_preset[1].bed_temp, self.material_preset[1].hotend_temp)

	def save_settings(self):
		print('saving settings')
		return True

	def setExtTemp(self, target, toolnum=0):
		self.sendGCode('M104 T%s S%s' % (toolnum, target))

	def setBedTemp(self, target):
		self.sendGCode('M140 S%s' % target)

	def preHeat(self, bedtemp, exttemp, toolnum=0):
		self.setBedTemp(bedtemp)
		self.setExtTemp(exttemp)

	def setZOffset(self, offset):
		self.sendGCode('SET_GCODE_OFFSET Z=%s MOVE=1' % offset)
  
	def SAVE_CONFIG(self):
		self.sendGCode('ACCEPT')
		self.sendGCode('SAVE_CONFIG')

	def AutoBedMesh(self):
		GCode = f'; CODE_START\n'
		GCode += 'M140 S60\n'
		self.sendGCode(GCode)
		GCode = 'M104 S150'
		self.sendGCode(GCode)
		if self.ishomed() == False:
			self.sendGCode('G28')
		GCode = 'M190 S60'
		self.sendGCode(GCode)
		GCode = 'M109 S150'
		self.sendGCode(GCode)
		GCode = 'BED_MESH_CALIBRATE PROFILE="default"'
		self.sendGCode(GCode)
		self.sendGCode('SAVE_CONFIG')
		self.sendGCode('; CODE_END')

	def Screw_Adjust(self,position_value):
		if (not self.ishomed()):
			self.sendGCode('G28')

		print(f'Screw_Adjust({position_value})')		
		x:int=-1
		y:int=-1
		max_x=self.X_MAX_POS
		max_y=self.Y_MAX_POS
		if (position_value) == 0:
			x= int(max_x*0.5)
			y= int(max_y*0.5)
		elif (position_value) == 1:
			x= int(max_x*0.166)
			y= int(max_y*0.166)
		elif (position_value) == 2:
			x= int(max_x*0.833)
			y= int(max_y*0.166)
		elif (position_value) == 3:
			x= int(max_x*0.833)
			y= int(max_y*0.833)
		elif (position_value) == 4:
			x= int(max_x*0.166)
			y= int(max_y*0.833)
		elif (position_value) == 5:
			x= int(max_x*0.5)
			y= int(max_y*0.166)
		elif (position_value) == 6:
			x= int(max_x*0.833)
			y= int(max_y*0.5)
		elif (position_value) == 7:
			x= int(max_x*0.5)
			y= int(max_y*0.833)
		elif (position_value) == 8:
			x= int(max_x*0.166)
			y= int(max_y*0.5)
		else:
			return
		GCode = 'G0 Z4 F5000\n'
		GCode += f'G1 X{x} Y{y} F5000\n'
		GCode += 'G4 P500\n'
		GCode += 'G0 Z1 F500\n'
		GCode += 'G0 Z0 F50\n'
		self.sendGCode(GCode)



	def Screws_Tilt_Calculate(self):
		GCode = f'; CODE_START\n'
		GCode += 'M140 S60\n'
		self.sendGCode(GCode)
		GCode = 'M104 S150'
		self.sendGCode(GCode)
		if self.ishomed() == False:
			self.sendGCode('G28')
		GCode = 'M190 S60'
		self.sendGCode(GCode)
		GCode = 'M109 S150'
		self.sendGCode(GCode)
  
		GCode = 'SCREWS_TILT_CALCULATE\n'
		self.sendGCode(GCode)


	def CalibratePID(self,target_pid,bed=False):
		GCode = f'; CODE_START\n'
		if (bed):
			GCode = f'PID_CALIBRATE HEATER=heater_bed TARGET={target_pid}'
		else:
			GCode = f'PID_CALIBRATE HEATER=extruder TARGET={target_pid}'
		self.sendGCode(GCode)
		GCode = f'G4 P1000\n'
		GCode += f'SAVE_CONFIG\n'
		GCode += f'; CODE_END\n'
		self.sendGCode(GCode)

  
	def Probe_Calibrate(self):
		if (not self.ishomed()):
			self.sendGCode('G28')
		x= int(self.X_MAX_POS*0.5)
		y= int(self.Y_MAX_POS*0.5)
		GCode = 'G0 Z4 F5000\n'
		GCode += f'G1 X{x} Y{y} F10000\n'
		GCode += f'PROBE_CALIBRATE\n'
		self.sendGCode(GCode)

	def Probe_Z_Test(self,z_offset,sign='+'):
		GCode = f'TESTZ Z={sign}{z_offset}\n'
		self.sendGCode(GCode)

	def Screws_Tilt_Calculate_Show(self) -> list[str]:
		print('Screws_Tilt_Calculate_Show()')
		screws_list: list[str] = []
		gcode_store = self.get_gcode_store(8)
		if not gcode_store:
			return screws_list

		for entry in gcode_store:
			entry_str = str(entry['message'])
			if ': adjust' in entry_str:
				screw_str = entry_str[entry_str.find(': adjust'):].replace(': adjust','').lstrip()
				screws_list.append(screw_str)
		return screws_list
	
	def Shaper_Calibrate(self, axis: str):
		GCode = "; CODE_START\n"
		if not self.ishomed():
			GCode += "G28\n"
		GCode += f"SHAPER_CALIBRATE AXIS={axis.upper()}\n"
		GCode += "SAVE_CONFIG\n"
		GCode += "; CODE_END\n"
		self.sendGCode(GCode)

	def emergency_stop(self):
		print("[DEBUG] emergency_stop() con M112")
		self.sendGCode("M112")

	


