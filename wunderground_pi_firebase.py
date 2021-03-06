#! /usr/bin/env python
#
# Fade an LED (or one color of an RGB LED) using GPIO's PWM capabilities.
#
# Usage:
#   sudo python colors.py 255 255 255
#
# @author Jeff Geerling, 2015

import csv
import sys

import numpy as np
from scipy import stats
from sklearn import linear_model
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline

import time

from collections import Counter
import math
from collections import defaultdict

import operator 
import json

import argparse
import time
#import RPi.GPIO as GPIO
#import pigpio
import pyrebase

import requests

from collections import defaultdict



#Firebase Configuration
config = {
  "apiKey": "apiKey",
  "authDomain": "weatherwhisperer.firebaseapp.com",
  "databaseURL": "https://weatherwhisperer.firebaseio.com",
  "storageBucket": "weatherwhisperer.appspot.com"
}

firebase = pyrebase.initialize_app(config)

#Firebase Database Intialization
db = firebase.database()

# LED pin mapping.
red = 17
green = 22
blue = 24
'''
# GPIO setup.
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(red, GPIO.OUT)
GPIO.setup(green, GPIO.OUT)
GPIO.setup(blue, GPIO.OUT)

# Set up colors using PWM so we can control individual brightness.
RED = GPIO.PWM(red, 100)
GREEN = GPIO.PWM(green, 100)
BLUE = GPIO.PWM(blue, 100)
RED.start(0)
GREEN.start(0)
BLUE.start(0)
'''

#pi = pigpio()

'''
Try five different models. Two kinds of linear regression plus polynomial regression with 
degree two, three, and four.
Use the R^2 value to pick the most accurate one
There are so few data points, We didn't want to hold any out for cross validation
and are aware that this makes us prone to overfitting. 
'''
def learn(features,target):
	best_score = 0
	best_model = 0
	X = np.matrix(features)
	Y = np.matrix(target)
	ml = -1

	for i in range(0,5):
		if i==0:
			clf = linear_model.LinearRegression()
			clf = clf.fit(X,Y)
		elif i==1:
			clf = linear_model.Ridge(alpha=0.5)
			clf = clf.fit(X,Y)	
		else:
			clf = make_pipeline(PolynomialFeatures(i), linear_model.Ridge())
			clf = clf.fit(X, Y)

		current_score = clf.score(X,Y)
		print(current_score)
		if abs(current_score)>abs(best_score):
			best_score = current_score
			best_model = clf
			ml = i

	print("Best model: ", ml)	
	return best_model

# Set a color by giving RGB values of 0-255. with GPIO
def setColor(r,g,b):
    # Convert 0-255 range to 0-100.
    red = (r/255.0) * 100
    blue = (b/255.0)*100
    green = (g/255.0)*100
    print(red)
    print(green)
    print(blue) 
    RED.ChangeDutyCycle(red)
    GREEN.ChangeDutyCycle(green)
    BLUE.ChangeDutyCycle(blue)

# Set a color by giving RGB values of 0-255. with GPIO
def setColor_Pig(r,g,b):
	pi.set_PWM_dutycycle(red, r)
	pi.set_PWM_dutycycle(green, g)
	pi.set_PWM_dutycycle(blue, b)
	print("Red: ",r)
	print("Green: ",g)
	print("Blue: ",b)

# Set hard limits between 0 and 255 for RGB balues
def hard_limits(color):
	if color > 255:
		return 255
	elif color < 0:
		return 0
	else:
		return color

#Determine whether or not we are confident in our prediction based on training data
#Currently based on whether a temperature, wind, and weather are near a training point
def test_sample(temp,wind,weather,temps,winds,weathers):
	confident_t = False
	confident_w = False
	confident_conds = False
	for t in temps:
		if abs(t-temp)<10:
			confident_t = True
	for w in winds:
		if abs(w-wind)<10:
			confident_w = True
	if weather in weathers:
		confident_conds = True

	confident = confident_t and confident_w and confident_conds
	return confident

#Predict the RGB values based on the current weather conditions
def predict(reg_model,city,state,weather_string,weather_float,features):
	
	r = requests.get('http://api.wunderground.com/api/8f5846f4c43e4050/conditions/q/'+state+'/'+city+'.json')
	values = r.json()
	temp = float(values["current_observation"]["temp_f"])
	wind = float(values["current_observation"]["wind_mph"])
	weather = weather_string[values["current_observation"]["weather"]]
	print([temp,wind,weather])
	temps = [f[0] for f in features]
	winds = [f[1] for f in features]
	weathers = [f[2] for f in features]
	confident = test_sample(temp,wind,weather,temps,winds,weathers)
	print("Confidence: ", confident)

	if confident:
		db.update({"learn":"Confident"})
	else:
		db.update({"learn":"Not Confident"})

	closest = reg_model.predict(np.matrix([[temp,wind,weather_float[weather]]]))
	red = int(np.round(closest[0][0]))
	green = int(np.round(closest[0][1]))
	blue = int(np.round(closest[0][2]))
	red = hard_limits(red)
	green = hard_limits(green)
	blue = hard_limits(blue)
	print(red,green,blue)
	return str(temp),str(wind), weather
	#setColor(red,green,blue)
	
#Add training point to database
def add_training_point(temp,wind,weather,r,g,b,total_training_points):
	id_ = total_training_points
	db.child("training").child("ID"+str(id_)).update({"temp":temp,"wind": wind,\
		"weather": weather,"red":r,"green":g,"blue":b})

#Extract historical information for a historical request
#Used for training app
def give_me_data(request):
	v = request.json()
	temp = v['history']['observations'][0]['tempi']
	wind = v['history']['observations'][0]['wspdi']
	weather = v['history']['observations'][0]['conds']
	print("temp_f: " + str(temp))
	print("wind_mph: " + str(wind))
	print("weather: " + str(weather))
	return temp,wind,weather
	
#Update the conditions if in the pre-training phase
def update_conditions(city,state,total_training_points):
	id_ = total_training_points
	temp = ""
	wind = ""
	weather = ""
	if(id_==0):
		history = 'history_20160115'
		r = requests.get('http://api.wunderground.com/api/8f5846f4c43e4050/'+history+'/q/'+state+'/'+city+'.json')
		temp,wind,weather = give_me_data(r)
	elif(id_==1):
		history = 'history_20160415'
		r = requests.get('http://api.wunderground.com/api/8f5846f4c43e4050/'+history+'/q/'+state+'/'+city+'.json')
		temp,wind,weather = give_me_data(r)
	elif(id_==2):
		history = 'history_20160715'
		r = requests.get('http://api.wunderground.com/api/8f5846f4c43e4050/'+history+'/q/'+state+'/'+city+'.json')
		temp,wind,weather = give_me_data(r)
	else:
		history = 'history_20161015'
		r = requests.get('http://api.wunderground.com/api/8f5846f4c43e4050/'+history+'/q/'+state+'/'+city+'.json')
		temp,wind,weather = give_me_data(r)

	return temp,wind,weather

#Grab the current weather conditions from the weather underground API
def current_conditions(city, state, weather_string):
	r = requests.get('http://api.wunderground.com/api/8f5846f4c43e4050/conditions/q/'+state+'/'+city+'.json')
	values = r.json()
	temp = float(values["current_observation"]["temp_f"])
	wind = float(values["current_observation"]["wind_mph"])
	weather = weather_string[values["current_observation"]["weather"]]
	return temp,wind,weather

#Extract features and target set for machine learning
def get_data(total_training_points,weather_float):
	features = []
	target = []
	for i in range(0,total_training_points):
		temp = float(db.child("training/ID"+str(i)+"/temp").get().val())
		wind = float(db.child("training/ID"+str(i)+"/wind").get().val())
		weather = db.child("training/ID"+str(i)+"/weather").get().val()
		red = float(db.child("training/ID"+str(i)+"/red").get().val())
		green = float(db.child("training/ID"+str(i)+"/green").get().val())
		blue = float(db.child("training/ID"+str(i)+"/blue").get().val())

		features.append([temp,wind,weather_float[weather]])
		target.append([red,green,blue])

	return features,target


#load weather descriptions
def load_conditions():
	weather = defaultdict(str)
	conditions = defaultdict(float)

	weather["Drizzle"]="Rain"
	weather["Rain"]="Rain"
	weather["Snow"]="Snow"
	weather["Snow Grains"]="Snow"
	weather["Ice Crystals"]="Snow"
	weather["Ice Pellets"]="Snow"
	weather["Hail"]="Snow"
	weather["Mist"]="Fog"
	weather["Fog"]="Fog"
	weather["Fog Patches"]="Fog"
	weather["Smoke"]="Cloudy"
	weather["Volcanic Ash"]="Cloudy"
	weather["Widespread Dust"]="Cloudy"
	weather["Sand"]="Cloudy"
	weather["Haze"]="Cloudy"
	weather["Spray"]="Rain"
	weather["Dust Whirls"]="Cloudy"
	weather["Sandstorm"]="Cloudy"
	weather["Low Drifting Snow"]="Snow"
	weather["Low Drifting Widespread Dust"]="Cloudy"
	weather["Low Drifting Sand"]="Cloudy"
	weather["Blowing Snow"]="Snow"
	weather["Blowing Widespread Dust"]="Cloudy"
	weather["Blowing Sand"]="Cloudy"
	weather["Rain Mist"]="Rain"
	weather["Rain Showers"]="Rain"
	weather["Snow Showers"]="Rain"
	weather["Snow Blowing Snow Mist"]="Snow"
	weather["Ice Pellet Showers"]="Snow"
	weather["Hail Showers"]="Rain"
	weather["Small Hail Showers"]="Rain"
	weather["Thunderstorm"]="Thunderstorm"
	weather["Thunderstorms and Rain"]="Thunderstorm"
	weather["Thunderstorms and Snow"]="Thunderstorm"
	weather["Thunderstorms and Ice Pellets"]="Thunderstorm"
	weather["Thunderstorms with Hail"]="Thunderstorm"
	weather["Thunderstorms with Small Hail"]="Thunderstorm"
	weather["Freezing Drizzle"]="Rain"
	weather["Freezing Rain"]="Rain"
	weather["Freezing Fog"]="Fog"
	weather["Patches of Fog"]="Fog"
	weather["Shallow Fog"]="Fog"
	weather["Partial Fog"]="Fog"
	weather["Overcast"]="Cloudy"
	weather["Clear"]="Sunny"
	weather["Partly Cloudy"]="Partly Cloudy"
	weather["Mostly Cloudy"]="Partly Cloudy"
	weather["Scattered Clouds"]="Partly Cloudy"
	weather["Small Hail"]="Rain"
	weather["Squalls"]="Rain"
	weather["Funnel Cloud"]="Cloudy"
	weather["Unknown Precipitation"]="Unknown"
	weather["Unknown"]="Unknown"

	conditions["Snow"]=10.0
	conditions["Rain"]=20.0
	conditions["Thunderstorm"]=25.0
	conditions["Fog"]=35.0
	conditions["Cloudy"]=40.0
	conditions["Partly Cloudy"]=45.0
	conditions["Clear"]=60.0
	conditions["Unknown"]=0.0

	return weather,conditions

#Get city and state info
def get_local():
	city = db.child("info/city").get().val()
	state = db.child("info/state").get().val()
	if city=="Washington D.C." or city == "Washington, D.C." or city=="Washington DC" or city == "Washington, DC":			
		city = "Washington"
		state = "DC"
		city = city.replace(" ","_")
	return city,state

if __name__ == "__main__":

	city = ""
	state = ""
	weather_string,weather_float = load_conditions()
	total_training_points=len(db.child("training").get().val())
	print(total_training_points)
	
	total = 0
	while True:
		status = db.child("pi_command").get().val()
		if(status=="on"):
			print("current status: ",status)
			city,state = get_local()
			features,target = get_data(total_training_points,weather_float)
			reg_model = learn(features,target)
			temp,wind,weather = predict(reg_model,city,state,weather_string,\
				weather_float,features) 
			db.child("current_conditions").update({"temp":temp,"wind": wind,\
				"weather": weather,"status":"updated"})
			db.update({"pi_command":"limbo"})

		#Keep track of current status
		if(status=="limbo"):
			time.sleep(10)
			total+=10
			if total>360:
				db.update({"pi_command":"on"})
				total = 0

		if(status=="location update"):
			print("current status: ",status)
			db.update({"learn":"training"})
			total_training_points=0
			db.update({"count":total_training_points})
			city,state = get_local()
			temp,wind,weather = current_conditions(city, state, weather_string)
			db.child("current_conditions").update({"temp":temp,"wind": wind,\
				"weather": weather,"status":"updated"})
			db.update({"pi_command":"off"})
		'''
		if(status=="off"):
			print("current status: ",status)
		'''

		if(status=="training point"):
			print("current status: ",status)
			temp = float(db.child("current_conditions/temp").get().val())
			wind = float(db.child("current_conditions/wind").get().val())
			weather = db.child("current_conditions/weather").get().val()
			r = int(db.child("color/red").get().val())
			g = int(db.child("color/green").get().val())
			b = int(db.child("color/blue").get().val())
			add_training_point(temp,wind,weather,r,g,b,total_training_points)
			if total_training_points >= 5:
				temp,wind,weather = current_conditions(city,state,weather_string)
			else: 
				temp,wind,weather = update_conditions(city,state,total_training_points)
			total_training_points+=1
			db.child("current_conditions").update({"temp":temp,"wind": wind,\
				"weather": weather,"status":"updated"})
			db.update({"pi_command":"off"})
		if(status=="done"):
			print("current status: ",status)
			break
			#pi.stop()
			#GPIO.cleanup()




