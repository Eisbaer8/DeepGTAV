#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from utils.Constants import IMG_WIDTH, IMG_HEIGHT


from deepgtav.messages import Start, Stop, Scenario, Dataset, Commands, frame2numpy, GoToLocation, TeleportToLocation, SetCameraPositionAndRotation
from deepgtav.messages import StartRecording, StopRecording
from deepgtav.messages import SetClockTime, SetWeather
from deepgtav.client import Client

from utils.BoundingBoxes import add_bboxes, parseBBox2d, convertBBoxesDeepGTAToYolo, parseBBox_YoloFormat_to_Image
from utils.utils import save_image_and_bbox, save_meta_data, getRunCount, generateNewTargetLocation
# import utils.BoundingBoxes 

import argparse
import time
import cv2

import matplotlib.pyplot as plt

from PIL import Image

from random import uniform

from math import sqrt
import numpy as np

import os



# Controls the DeepGTAV vehicle
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=None)
    parser.add_argument('-l', '--host', default='localhost', help='The IP where DeepGTAV is running')
    parser.add_argument('-p', '--port', default=8000, help='The port where DeepGTAV is running')
    # parser.add_argument('-s', '--save_dir', default='E:\\Bachelorarbeit\\DataGeneration_DeepGTAV-PreSIL\\EXPORTDIR_OWN', help='The directory the generated data is saved to')
    parser.add_argument('-s', '--save_dir', default='Z:\\DeepGTAV-EXPORTDIR-TEST\\Generation13_LOW_HEIGHT_VARIABLE_CAMERA', help='The directory the generated data is saved to')
    args = parser.parse_args()

    # TODO for running in VSCode
    # args = parser.parse_args('')
    
    args.save_dir = os.path.normpath(args.save_dir)

    client = Client(ip=args.host, port=args.port)
    



    # We set the scenario to be in manual driving, and everything else random (time, weather and location). 
    # See deepgtav/messages.py to see what options are supported
    # scenario = Scenario(drivingMode=-1) #manual driving (Works, but is too slow to be used)
    # scenario = Scenario(drivingMode=786603) #automatic driving
    # scenario = Scenario(drivingMode=786603, vehicle="buzzard") #automatic driving
    # scenario = Scenario(drivingMode=786603, vehicle="buzzard", location=[-424.991, -522.049, 50]) #automatic driving
    scenario = Scenario(drivingMode=786603, vehicle="buzzard", location=[245.23306274414062, -998.244140625, 29.205352783203125]) #automatic driving
    # scenario = Scenario(drivingMode=[786603, 20.0], vehicle="buzzard", location=[275.23306274414062, -998.244140625, 29.205352783203125]) #automatic driving
    # scenario = Scenario(drivingMode=-1, vehicle="buzzard") #automatic driving

    dataset=Dataset(location=True, time=True)

    client.sendMessage(Start(scenario=scenario, dataset=dataset))
    

    CAMERA_OFFSET_Z = -20
    CAMERA_ROT_X_LOW = -90
    CAMERA_ROT_X_HIGH = -20

    # With rot_y = 180
    # rot_x in 90 - 180 is correct

    # Adjustments for recording from UAV perspective
    client.sendMessage(SetCameraPositionAndRotation(z = CAMERA_OFFSET_Z, rot_x = uniform(CAMERA_ROT_X_LOW, CAMERA_ROT_X_HIGH)))

    # Start listening for messages coming from DeepGTAV. We do it for 20 hours

    stoptime = time.time() + 20 * 3600
    count = 0
    bbox2d_old = ""
    errors = []



    # SETTINGS
    STARTING_COUNT = 100


    TRAVEL_HEIGHT_LOW = 20
    TRAVEL_HEIGHT_HIGH = 40

    currentTravelHeight = uniform(TRAVEL_HEIGHT_LOW, TRAVEL_HEIGHT_HIGH)
    x_target, y_target = generateNewTargetLocation(-1200, 1400, -2200, 1300)
    # x_target, y_target = (-182.139, -507.529)

    if not os.path.exists(os.path.join(args.save_dir, 'images')):
        os.makedirs(os.path.join(args.save_dir, 'images'))
    if not os.path.exists(os.path.join(args.save_dir, 'labels')):
        os.makedirs(os.path.join(args.save_dir, 'labels'))
    if not os.path.exists(os.path.join(args.save_dir, 'meta_data')):
        os.makedirs(os.path.join(args.save_dir, 'meta_data'))
        

    run_count = getRunCount(args.save_dir)


    while True:
        try:
            # We receive a message as a Python dictionary
            count += 1
            print("count: ", count)

            # Only record every 10th frame
            if count > STARTING_COUNT and count % 10 == 0:
                client.sendMessage(StartRecording())
            if count > STARTING_COUNT and count % 10 == 1:
                client.sendMessage(StopRecording())


            if count == 2:
                client.sendMessage(TeleportToLocation(x_target, y_target, 200))
            if count == 4:
                client.sendMessage(SetClockTime(int(uniform(0,24))))


            message = client.recvMessage()  
            
            # None message from utf-8 decode error
            # TODO this should be managed better
            if message == None:
                continue


            # Generate a new Travelheight for every x frames (which are x / 10 recorded frames):
            if count % 500 == 0:
                currentTravelHeight = uniform(TRAVEL_HEIGHT_LOW, TRAVEL_HEIGHT_HIGH)
            
            if count % 700 == 0:
                client.sendMessage(SetCameraPositionAndRotation(z = CAMERA_OFFSET_Z, rot_x = uniform(CAMERA_ROT_X_LOW, CAMERA_ROT_X_HIGH)))


            
            estimated_ground_height = message["location"][2] - message["HeightAboveGround"]

            # Sometimes Generate a new location, to prevent getting stuck
            if count % 2000 == 0:
                x_target, y_target = generateNewTargetLocation(-1200, 1400, -2200, 1300)
                client.sendMessage(GoToLocation(x_target, y_target, estimated_ground_height + currentTravelHeight))



            # if we are near the target location generate a new target location
            if sqrt((message["location"][0] - x_target) ** 2 + (message["location"][1] - y_target) ** 2) < 10:
                x_target, y_target = generateNewTargetLocation(-1200, 1400, -2200, 1300)
                client.sendMessage(GoToLocation(x_target, y_target, estimated_ground_height + currentTravelHeight))
                print("Going to new loctation: ", x_target, y_target, currentTravelHeight)



            # keep the currentTravelHeight under the wanted one
            # Move a little bit in the desired direction but primarily correct the height
            if message["HeightAboveGround"] > currentTravelHeight + 3 or message["HeightAboveGround"] < currentTravelHeight - 3:
                direction = np.array([x_target - message["location"][0], y_target - message["location"][1]])
                direction = direction / np.linalg.norm(direction)
                direction = direction * 50
                x_temporary = message["location"][0] + direction[0]
                y_temporary = message["location"][1] + direction[1]
                client.sendMessage(GoToLocation(x_temporary, y_temporary, estimated_ground_height + currentTravelHeight))
                print("Correcting height")
            else:
                client.sendMessage(GoToLocation(x_target, y_target, estimated_ground_height + currentTravelHeight))

            # print("current target: ", x_target, y_target, currentTravelHeight)
            # print("current location: ", message["location"])
            # print("HeightAboveGround: ", message["HeightAboveGround"])

            # print("vehicles: ", message["vehicles"])
            # print("peds: ", message["peds"])
            # print("location: ", message["location"])
            # print("index: ", message["index"])
            # print("focalLen: ", message["focalLen"])
            # print("curPosition: ", message["curPosition"])
            # print("seriesIndex: ", message["seriesIndex"])
            # print("bbox2d: ", message["bbox2d"])

            if message["bbox2d"] != bbox2d_old and message["bbox2d"] != None:
                try: # Sometimes there are errors with the message, i catch those here

                    # save Data
                    # Use filename of the format [run]_[count] with padding, e.g. for the 512th image in the 21th run:
                    # 0021_000000512
                    filename = f'{run_count:04}' + '_' + f'{count:010}'
                    bboxes = convertBBoxesDeepGTAToYolo(message["bbox2d"])
                    if bboxes != "":
                        save_image_and_bbox(args.save_dir, filename, frame2numpy(message['frame'], (IMG_WIDTH,IMG_HEIGHT)), bboxes)
                        save_meta_data(args.save_dir, filename, message["location"], message["HeightAboveGround"], message["CameraPosition"], message["CameraAngle"], message["time"], "CLEAR")
                        
                    
                    # img = add_bboxes(frame2numpy(message['frame'], (IMG_WIDTH,IMG_HEIGHT)), parseBBox_YoloFormat_to_Image(bboxes))
                    # cv2.imshow("test", img)
                    # cv2.waitKey(1) 
                    bbox2d_old = message["bbox2d"]
                except Exception as e:
                    print(e)
                    errors.append(e)

            
        except KeyboardInterrupt:
            break
            
    # We tell DeepGTAV to stop
    client.sendMessage(Stop())
    client.close()

