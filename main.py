# Jamorham - Google App Engine - cloud based receiver.cgi for Parakeet

# Parakeet Wixel Firmware uploads data to google app engine instance - requires version after 15th Dec 2015
# xDrip software uses http(s) source to retreive data. Requires version after 15th Dec 2015 (jamorham fork)

# Data is stored in memory cache within google and expires after 24 hours (maximum)
# Backfilling is possible up to max_memcache_entries (default 1 hour)

# App engine instance can be shared with multiple users as they are multiplexed by transmitter id and secure
# with passcode. Free quota limits might be an issue with more than a couple of users.

# When you deploy your own App Engine instance using this script, connect immediately to the front page
# to register yourself as the admin user. The first logged in google user which connects to the front page
# becomes the admin user. To reset the admin user you would need to purge the datastore from the developers console.

import json
import time
from os import environ

from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import ndb

from flask import Flask
from flask import Response
from flask import escape
from flask import redirect
from flask import request

# Global variables

# How many entries we can backfill, less means google has to store and process less data, more gives
# longer backfill. Google memcache performance quota is unknown but these datasets are very small
# one entry per 5 minutes, 12 = 1 hour backfill
max_memcache_entries = 12

# If passcode is required then without the passcode you cannot retreive the data even if you knew or
# guessed a transmitter id. If you don't want to bother with setting a passcode then you can set this to false.
require_passcode = True

use_geolocation = True

google_maps_url = "https://maps.google.com/?q="

# INSTRUCTIONS FOR CONFIGURING PARAKEET

# To configure the parakeet for use with google app engine, send a set of text messages like:

# HTTP parakeet-receiver.appspot.com/receiver.cgi
# --- replace parakeet-receiver above with your own appspot project sub domain.
# --- You can use my parakeet-receiver app engine instance for testing if you like.

# UDP disabled 12345
# --- replace 12345 with your secret pass code which you create here (5 digits). This pass code ensures that it is
# --- very hard for a random person to retrieve your data even from an app engine instance shared between users.
# --- Whatever passcode you set, you also have to put it in to the xdrip app as described below.
# --- We are reusing the UDP Port number setting on the Parakeet to function as a passcode for use
# --- with the cloud hosted version (which does not support UDP)

# APN yourcarriers.apn.address
# --- This must match the GPRS apn address supplied by your sim card provider.

# TRANSMIT ABCDE
# --- Replace ABCDE with your dexcom transmitter number. Send this command last as it will switch the
# --- Parakeet in to deep sleeping mode where the GSM feature will be switched off except during upload.


# INSTRUCTIONS FOR CONFIGURING XDRIP APP

# Within the xDrip app set the Hardware Data Source to include Wifi Wixel and in the list of receivers add
# http://<your google app engine name>.appspot.com/<your transmitter id>/<your passcode>/json.get

# if you have set require_passcode = False then use
# http://<your google app engine name>.appspot.com/<your transmitter id>/json.get

# If you want to add an extra layer of privacy you can use https:// instead of http:// but this will
# increase data usage

# INSTRUCTIONS FOR VIEWING THE GEOLOCATION MAP

# Use xDrip+ and enable Settings -> Extra test/parakeet features and then find "Show Parakeet Map" on the
# right side menu of the home screen. https://jamorham.github.io#xdrip-plus

# Alternatively, open your browser and visit and bookmark the url:
# https://<your google app engine name>.appspot.com/<your transmitter id>/<your passcode>/map.get

# This might be a little tricky because this url immediately redirects to google maps - on chrome you can
# do this with bookmarks -> manage bookmarks -> (right click) add page




# Set to True when in development
master_debug = environ['SERVER_SOFTWARE'].startswith('Development')

# Output Template
mydata = {"TransmitterId": "0", "_id": 1, "CaptureDateTime": 0, "RelativeTime": 0,
		  "RawValue": 0, "TransmissionId": 0, "BatteryLife": 0, "UploaderBatteryLife": 0, "FilteredValue": 0,
		  "GeoLocation": ""}


# Functions

def save_record_to_memcache(this_set, my_data, write_only=False):
	ret_val = 0
	mcname = '{}alldata'.format(this_set)

	if write_only:
		current = memcache.get(mcname)
		if type(current) is int:
			ret_val = current
		current = my_data

	else:
		current = memcache.get(mcname)
		if (current == None):
			current = []
		elif type(current) is int:
			ret_val = current
			current = []
		if (len(current) > 0):
			datum = current[0]  # first item only
			if (datum['FilteredValue'] == my_data['FilteredValue'] and datum['RawValue'] == my_data['RawValue'] and (
					datum['GeoLocation'] != "-15,-15" or my_data['GeoLocation'] == "-15,-15")):
				return -1  # dupe

			if (datum['GeoLocation'] == "-15,-15") and (my_data['GeoLocation'] != "-15,-15"):
				datum['GeoLocation'] = my_data['GeoLocation']  # update to show parakeet geo location
				datum['UploaderBatteryLife'] = my_data['UploaderBatteryLife']  # update to show parakeet geo location
			else:
				current = [my_data] + current   # not updated so add this record
		else:
				current = [my_data] + current	# empty data set add first record

		if (len(current) > max_memcache_entries):
			del current[-1]
	memcache.set(mcname, current, 86400)
	return ret_val


def get_cached_records(this_set, numberOfRecords):
	mcname = '{}alldata'.format(this_set)
	current = memcache.get(mcname)
	memcache.set(mcname, current, 86400) # refresh it to keep alive
	reply = ""
	if (current == None) or type(current) is int:
		current = []
	for this_record in current:
		reply += json.dumps(update_relative_time_json(this_record), sort_keys=master_debug) + "\n"
		numberOfRecords = numberOfRecords - 1
		if (numberOfRecords == 0):
			return reply
	return reply


def update_relative_time_json(this_data):
	if (this_data['RawValue'] != 0):
		this_data['RelativeTime'] = str((int(time.time()) * 1000) - int(this_data['CaptureDateTime']))
		return this_data
	else:
		return None


def get_alldata(this_set):
	mcname = '{}alldata'.format(this_set)
	datum = memcache.get(mcname)  # read existing if any
	return datum


def is_this_different_record_json(this_set, lr, lf):
	mcname = '{}alldata'.format(this_set)
	datum = memcache.get(mcname)  # read existing if any
	if datum is None or type(datum) is int:
		return True
	datum = datum[0]  # first item only
	if (datum['FilteredValue'] != lf or datum['RawValue'] != lr):
		return True
	return False


SrcNameTable = ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
				'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K',
				'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'U', 'W',
				'X', 'Y')


def getSrcValue(srcVal):
	return SrcNameTable.index(srcVal)


def dex_src_to_asc(para):
	src = long(para)
	addr = ""
	addr += SrcNameTable[(src >> 20) & 0x1F]
	addr += SrcNameTable[(src >> 15) & 0x1F]
	addr += SrcNameTable[(src >> 10) & 0x1F]
	addr += SrcNameTable[(src >> 5) & 0x1F]
	addr += SrcNameTable[(src >> 0) & 0x1F]
	return addr


def asciiToDexSrc(addr):
	src = 0
	src |= (getSrcValue(addr[0]) << 20)
	src |= (getSrcValue(addr[1]) << 15)
	src |= (getSrcValue(addr[2]) << 10)
	src |= (getSrcValue(addr[3]) << 5)
	src |= getSrcValue(addr[4])
	return long(src)


# Object defintions

class legacy:
	def __init__(self):
		self.lv = ""
		self.lf = ""
		self.ts = ""
		self.bp = ""
		self.bm = ""
		self.gl = ""
		self.ct = ""
		self.db = ""
		self.zi = ""
		self.pc = ""


class AdminUser(ndb.Model):
	user = ndb.StringProperty()


# Main

app = Flask(__name__)


# Front page
@app.route('/')
def hello_world():
	user = users.get_current_user()
	if user:
		thisAdminUser = AdminUser.get_by_id('adminuser')
		if (thisAdminUser):
			if (user.email() == thisAdminUser.user):
				reply = json.dumps(memcache.get_stats(), sort_keys=True) + "\n"
				reply += "Debug: " + str(master_debug)
				return Response(reply + "\n", mimetype='text/plain')
			else:
				return "Hello " + user.nickname() + " you are logged in but are not the owner of this app."
		else:
			AdminUser(id='adminuser', user=user.email()).put()
			return "Admin user set to: " + user.email()
	else:
		return "<a href=\"" + users.create_login_url() + "\">Please login</a>"


# Prevent indexing
@app.route('/robots.txt')
def blockrobots():
	return Response("User-agent: *\nDisallow: /\n", mimetype='text/plain')


# Data input from Parakeet
@app.route('/receiver.cgi')
def parakeetreceiver():
	try:
		# backwards legacy code for attributes and expecting string
		# params
		data = legacy()
		data.lv = request.args.get('lv', "0", type=str)
		data.lf = request.args.get('lf', "0")
		data.ts = request.args.get('ts', "0")
		data.bp = request.args.get('bp', "0")
		data.bm = request.args.get('bm', "0")
		data.gl = request.args.get('gl', "")
		data.ct = request.args.get('ct', "0")
		data.db = request.args.get('db', "0")
		data.zi = request.args.get('zi', "0")
		data.pc = request.args.get('pc', "")

		ret_val = 0

		if (data.lv != "") and (((int(data.lv) > 0) and (int(data.lf) > 0) and (int(data.ts) > 0)) or (
					str(int(data.zi)) == "10858926")):

			mydata['CaptureDateTime'] = str(int(time.time()) - (int(data.ts) / 1000)) + "000"
			mydata['RelativeTime'] = "0"
			mydata['RawValue'] = data.lv
			mydata['FilteredValue'] = data.lf
			mydata['UploaderBatteryLife'] = data.bp
			mydata['BatteryLife'] = str(int(data.db))
			if (data.zi != "0"):
				mydata['TransmitterId'] = str(int(data.zi))  # might need conversion back to ascii
			else:
				return "ERR - no transmitter id - upgrade"

			# don't forget the GL parameter!
			ascii_tx_id = dex_src_to_asc(int(data.zi))
			if (master_debug == True):
				reply = "!ACK" + "-" + ascii_tx_id
			else:
				reply = "!ACK "

			if (use_geolocation == True) and str(int(data.zi)) != "10858926":
				mydata['GeoLocation'] = data.gl
			else:
				mydata['GeoLocation'] = ""

			if (require_passcode == True):
				ascii_tx_id = ascii_tx_id + "-" + data.pc

			ret_val = save_record_to_memcache(ascii_tx_id, mydata)
		else:
			reply = "ERR"
		if (ret_val > -1):
			return reply + " " + str(ret_val) + "!"
		else:
			return "!ACK dupe"


	except Exception, e:
		if (master_debug):
			raise  # debug only
		return "Got exception: " + str(e)


# custom functions to be executed on the parakeet itself, code=2 is stop sleeping
@app.route('/<transmitter_id>/<pass_code>/setcode/<code>')
def nosleep_transmitter_and_passcode(transmitter_id, pass_code, code):
	code = int(code)
	if (require_passcode == True):
		ret_val = save_record_to_memcache(transmitter_id + "-" + pass_code, code, write_only=True)
		return "OK " + str(ret_val)
	else:
		ret_val = save_record_to_memcache(transmitter_id, code, write_only=True)
		return "OK" + str(ret_val)


@app.route('/<transmitter_id>/setcode/<code>')
def no_sleep_transmitter_only(transmitter_id, code):
	code = int(code)
	if (require_passcode == True):
		return "require_passcode is set to True"
	save_record_to_memcache(transmitter_id, code, write_only=True)
	return "OK"


# Data Output

# mode not requiring passcode
@app.route('/<transmitter_id>/json.get')
def transmitter_only(transmitter_id):
	if (require_passcode == True):
		return "require_passcode is set to True"
	return json_output(transmitter_id)


# mode including passcode with lazy fallback option
@app.route('/<transmitter_id>/<pass_code>/json.get')
def transmitter_and_passcode(transmitter_id, pass_code):
	if (require_passcode == True):
		return json_output(transmitter_id + "-" + pass_code)
	else:
		return json_output(transmitter_id)


# mode including passcode for map link if enabled
@app.route('/<transmitter_id>/<pass_code>/map.get')
def geo_map(transmitter_id, pass_code):
	datum = get_alldata(transmitter_id + "-" + pass_code)
	if (datum == None):
		return "No data"
	if (require_passcode == True) and (use_geolocation == True):
		for this_record in datum:
			url = google_maps_url + str(escape(this_record['GeoLocation']))
			return redirect(url, code=302)
	else:
		return "Will not show map without passcode and use_geolocation enabled"


def json_output(transmitter_id):
	numberOfRecords = request.args.get('n', 1, type=int)
	if (numberOfRecords > 100):
		numberOfRecords = 100

	reply = ""

	if (transmitter_id != None) and (transmitter_id != ""):
		# do we need to filter valid chars or just bounce an exception?
		tmp_reply = get_cached_records(transmitter_id, numberOfRecords)

		if (tmp_reply != None) and (tmp_reply != ""):
			reply = reply + tmp_reply

	return Response(reply + "\n", mimetype='text/plain')


if __name__ == '__main__':
	app.run(debug=master_debug)
