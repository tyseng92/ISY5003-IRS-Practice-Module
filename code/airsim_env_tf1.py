import airsim
import numpy as np
import config
from geopy import distance
from DroneControlAPI_yv4 import DroneControl

import time
import itertools

clockspeed = 1
timeslice = 0.5 / clockspeed
goalY = 57
outY = -0.5
angle_spd = 10

# distance sensor config
dsensor_num = 8
dsensor_thrd = 10

focus_size = 0.7

# spread threshold
spread_thd = 5

# best area score list
#best_area = [0, 0, 0] 

# base on UE4 coordinate with NED frame
floorZ = 0 
min_height = -7 
max_height = -9
min_x = -20
max_x = 20
min_y = -40
max_y = 40
small_boundary_ratio = 0.85
min_small_x = min_x * small_boundary_ratio
max_small_x = max_x * small_boundary_ratio
min_small_y = min_y * small_boundary_ratio
max_small_y = max_y * small_boundary_ratio

# number of target to success
target_num = 1

goals = [7, 17, 27.5, 45, goalY]
speed_limit = 0.2
ACTION = ['00', '+x', '+y', '+rz', '-x', '-y', '-rz']

droneList = ['Drone0', 'Drone1', 'Drone2']
yolo_weights = 'data/drone.h5'

class Env:
    def __init__(self):
        # connect to the AirSim simulator
        self.dc = DroneControl(droneList)

        self.action_size = 3
        self.altitude = -8
        #self.altitude = -2.5
        self.init_pos = [0,0,self.altitude]
        self.camList = [0,1,2,4]
        #self.camera_angle = [-50, 0, 0]
        self.camera_angle = [[-50, 0, 90], [-50, 0, -90], [-50, 0, 0], [-50, 0, 0]] 
        self.best_area = [0, 0, 0]

        # initialize gps origin for distance calculation
        self.gps_origin = []
        for drone in droneList:
            gps = self.dc.getGpsData(drone)
            self.gps_origin.append((gps.latitude, gps.longitude))

    def capture_state_image(self):
        # all of the drones take image.
        responses = []
        for drone in droneList:
            response = []
            for camID in self.camList:
                while True:
                    #self.dc.getImage(drone)
                    img = self.dc.captureImgNumpy(drone, cam = camID)
                    if img.size != 0:
                        #print("ImageCaptured!")
                        break
                    print("Img is None.")
                response.append(img)
            responses.append(response)
        return responses

    def capture_state_dist_gps(self):
        # get drone distance from origin using GPS position.
        drone_dist = []
        for id, drone in enumerate(droneList):
            gps = self.dc.getGpsData(drone)
            gps_drone = (gps.latitude, gps.longitude)
            dist = distance.distance(self.gps_origin[id], gps_drone).m
            drone_dist.append(dist)
            print("Drone distance from origin: ", dist)
        return np.array(drone_dist)

    def capture_state_dist_imu(self):
        # Alternative way of getting drone distance from origin using IMU position.
        drone_dist = []
        for drone in droneList:
            pos = self.dc.getDronePosition(drone)
            # distance from origin to drone
            dist = np.linalg.norm([pos.x_val, pos.y_val])
            drone_dist.append(dist)
            print("Drone distance from origin: ", dist)
        return np.array(drone_dist)

    def capture_state_position(self):
        drone_pos = []
        for drone in droneList:
            pos = self.dc.getDronePosition(drone)
            drone_pos += [pos.x_val, pos.y_val, pos.z_val]
        return np.array(drone_pos)


    def capture_state_speed(self):
        quad_spd = []
        for drone in droneList:
            quad_vel = self.dc.getMultirotorState(drone).kinematics_estimated.linear_velocity
            quad_vel_vec = [quad_vel.x_val, quad_vel.y_val, quad_vel.z_val]
            quad_spd_val = np.linalg.norm(quad_vel_vec)
            quad_spd.append(quad_spd_val)
            print("Drone speed: ", quad_spd_val)
        return quad_spd

    def nested_list_to_list(self, responses):
        # convert responses from nested list into list. Used all of the images captured by drones.
        obs_responses = []
        for imglist in responses:
            for img in imglist:
                obs_responses.append(img) 
        print("obs_responses len: ", len(obs_responses)) 
        return obs_responses

    def reset(self):
        '''
        Method to reset AirSim env to starting position
        '''
        print("RESET")
        self.dc.resetAndRearm_Drones()
        self.dc.reset_area()
        self.best_area = [0, 0, 0]

        # all drones takeoff
        self.dc.simPause(False)
        for drone in droneList:
            print(f'{drone} taking off...')
            #self.dc.moveDrone(drone, [0,0,-1], 2 * timeslice)
            #self.dc.moveDrone(drone, [0,0,0], 0.1 * timeslice)
            self.dc.moveDroneToPos(drone, self.init_pos)
            self.dc.hoverAsync(drone).join()
            #self.camera_angle = [-50, 0, 0]
            self.camera_angle = [[-50, 0, 90], [-50, 0, -90], [-50, 0, 0], [-50, 0, 0]] 
            self.dc.setCameraAngle(self.camera_angle[0], drone, cam="1")
            self.dc.setCameraAngle(self.camera_angle[1], drone, cam="2")
            self.dc.setCameraAngle(self.camera_angle[2], drone, cam="4")
            self.dc.setCameraAngle(self.camera_angle[3], drone, cam="0")
            
        # Initial image capturing by drones
        responses = self.capture_state_image()

        # get drone distance from origin using GPS position.
        drone_dist = self.capture_state_position()

        # convert responses from nested list into list. Used all of the images captured by drones.
        obs_responses = self.nested_list_to_list(responses)  

        observation = [obs_responses, drone_dist]
        return observation

    def step(self, quad_offset_list):
        print("STEP")
        # move with given velocity
        quad_offset = []
        for qoffset in quad_offset_list: # [(xyz),(xyz),(xyz)]
            quad_offset.append([float(i) for i in qoffset])
        self.dc.simPause(False)
        
        # Move the drones
        cam_shifted = [0,0,0]
        for id, drone in enumerate(droneList):
            self.dc.changeDroneAlt(drone, -8)

            # if quad_offset has length of 3, run continuous action.
            if len(quad_offset[id]) == 3:
                self.dc.moveDroneBySelfFrame(drone, [quad_offset[id][0],quad_offset[id][1],0], 5*timeslice) # 2*timeslice 
                self.stabilize(drone)
                self.camera_angle[0][2] += quad_offset[id][2]*angle_spd
                self.camera_angle[1][2] += quad_offset[id][2]*angle_spd
                self.camera_angle[2][2] += quad_offset[id][2]*angle_spd
                self.camera_angle[3][2] += quad_offset[id][2]*angle_spd
                self.dc.setCameraAngle(self.camera_angle[0], drone, cam="1")
                self.dc.setCameraAngle(self.camera_angle[1], drone, cam="2")
                self.dc.setCameraAngle(self.camera_angle[2], drone, cam="4")
                self.dc.setCameraAngle(self.camera_angle[3], drone, cam="0")

                cam_shifted[id] = quad_offset[id][2]*angle_spd

            # else run discrete action.
            else:
                # front or back
                if quad_offset[id][3] == 1 or quad_offset[id][3] == 4:
                    self.dc.moveDroneBySelfFrame(drone, [quad_offset[id][0],0,0], 5*timeslice) # 2*timeslice 
                    self.stabilize(drone)
                    #self.dc.changeDroneAlt(drone, -8)
                # left or right
                elif quad_offset[id][3] == 2 or quad_offset[id][3] == 5:
                    #self.dc.turnDroneBySelfFrame(drone, quad_offset[id][1]*angle_spd, 5*timeslice) # 2*timeslice
                    self.dc.moveDroneBySelfFrame(drone, [0,quad_offset[id][1],0], 5*timeslice) # 2*timeslice 
                    self.stabilize(drone)
                    #self.dc.changeDroneAlt(drone, -8)
                # cam left or right
                elif quad_offset[id][3] == 3 or quad_offset[id][3] == 6:
                    #self.camera_angle[2] += quad_offset[id][2]*angle_spd
                    #self.dc.setCameraAngle(self.camera_angle, drone)
                    self.camera_angle[0][2] += quad_offset[id][2]*angle_spd
                    self.camera_angle[1][2] += quad_offset[id][2]*angle_spd
                    self.camera_angle[2][2] += quad_offset[id][2]*angle_spd
                    self.camera_angle[3][2] += quad_offset[id][2]*angle_spd
                    self.dc.setCameraAngle(self.camera_angle[0], drone, cam="1")
                    self.dc.setCameraAngle(self.camera_angle[1], drone, cam="2")
                    self.dc.setCameraAngle(self.camera_angle[2], drone, cam="4")
                    self.dc.setCameraAngle(self.camera_angle[3], drone, cam="0")

                    cam_shifted[id] = quad_offset[id][2]*angle_spd

                # top and bottom
                # elif quad_offset[id][3] == 3 or quad_offset[id][3] == 6:
                #     self.dc.moveDroneBySelfFrame(drone, [0,0,quad_offset[id][2]], 2* timeslice)
                #     self.stabilize(drone)
                # for stop action quad_offset[id][3] == 0 
                else:
                    pass 

                # print("camera_angle_action:", self.camera_angle[0][2])
                # print("camera_angle_action:", self.camera_angle[1][2])
                # print("camera_angle_action:", self.camera_angle[2][2])
                # print("camera_angle_action:", self.camera_angle[3][2])

                #self.dc.moveDrone(drone, [quad_offset[id][0], quad_offset[id][1], quad_offset[id][2]], 2* timeslice)

        # Get follower drones position and linear velocity        
        landed = [False, False, False]
        collided = [False, False, False]
        has_collided = [False, False, False]
        collision_count = [0, 0, 0]

        start_time = time.time()
        while time.time() - start_time < timeslice:
            # get quadrotor states
            quad_pos = []
            quad_vel = []
            for drone in droneList:
                #quad_pos.append(self.dc.getMultirotorState(drone).kinematics_estimated.position)
                quad_pos.append(self.dc.getDronePosition(drone))
                quad_vel.append(self.dc.getMultirotorState(drone).kinematics_estimated.linear_velocity)

            # decide whether collision occured
            for id, drone in enumerate(droneList):
                collided[id] = self.dc.simGetCollisionInfo(drone).has_collided
                land = (quad_vel[id].x_val == 0 and quad_vel[id].y_val == 0 and quad_vel[id].z_val == 0)
                landed[id] = land or quad_pos[id].z_val > floorZ
                collision = collided[id] or landed[id]
                if collision:
                    collision_count[id] += 1
                if collision_count[id] > 10:
                    has_collided[id] = True
                    break
            if any(has_collided):
                break

        self.dc.simPause(True)
        #time.sleep(1)

        # all of the drones take image
        responses = self.capture_state_image()

        # get drone distance from origin using GPS position.
        #drone_dist = self.capture_state_dist_gps()
        drone_dist = self.capture_state_position()

        # get drone position from IMU 
        drone_pos = []
        for drone in droneList:
            drone_pos.append(self.dc.getDronePosition(drone)) 

        # calculate the gaps distance between drones, and determine the spread reward.
        spread_reward = 'far'
        pos_comb = itertools.combinations(drone_pos, 2)
        drone_spread = 0
        for com in pos_comb:
            drone_spread = np.linalg.norm([com[0].x_val - com[1].x_val, com[0].y_val - com[1].y_val])
            if drone_spread <= spread_thd:
                spread_reward = 'near'
                break
        # determine spread reward 
        # if total_spread <= spread_thd:
        #     spread_reward = 'near'
        print('spread_reward: ', spread_reward)

        # penalty for distance sensor
        dsensor_reward = [False, False, False]
        for id, drone in enumerate(droneList):
            for i in range(1,dsensor_num+1):
                dsensor = "Distance" + str(i)
                dist_sensor = self.dc.getDistanceData(dsensor, drone).distance
                if dist_sensor <= dsensor_thrd:
                    dsensor_reward[id] = True
                    break
            #print("dist_sensor: ", dist_sensor)
        print("dsensor_reward: ", dsensor_reward)
        # quad_spd = [] 
        # for drone in droneList:
        #     quad_vel = self.dc.getMultirotorState(drone).kinematics_estimated.linear_velocity
        #     quad_vel_vec = [quad_vel.x_val, quad_vel.y_val, quad_vel.z_val]
        #     quad_spd_val = np.linalg.norm(quad_vel_vec)
        #     quad_spd.append(quad_spd_val)
        #     print("drone speed: ", quad_spd_val)
        
        # Get image reward from drones
        exist_reward = {}
        focus_reward = {}
        #size_reward = {}
        success = [False, False, False]
        for id, drone in enumerate(droneList):
            for camid in range(len(self.camList)):
                img = responses[id][camid]
                #try:
                bboxes = self.dc.predict_yv4(img)
                    
                # if no detection is found, where bbox is [0,0,0,0].
                if bboxes == [] or bboxes == None:
                    exist_status = 'miss'
                    exist_reward[id] = exist_status
                    focus_status = 'none' 
                    focus_reward[id] = focus_status
                    #size_status = 'none'
                    #size_reward[id] = size_status
                # if there is detection found in image.
                else:
                    bbox = bboxes[0] # get first detection only
                    exist_status = 'found'
                    exist_reward[id] = exist_status

                    focus_status = self.check_focus(bbox, img)
                    focus_reward[id] = focus_status

                    #size_status = self.check_size(bbox, img)
                    #size_reward[id] = size_status

                    # done if target is found within range 
                    if focus_status == "in":
                        success[id] = True
                        # need to break out once found target in one of the cam for every drone
                        break
                    #break

            #print(f'Drone[{id}] status: [{exist_status}], [{focus_status}], [{size_status}]')
        print("Success: ", success)

        # Get area reward from drones
        area_reward = {}
        for id, drone in enumerate(droneList):
            #print("cam_shifted: ", cam_shifted[id])
            cal_reward = self.dc.testAreaCoverage(drone, self.camList, cam_shifted[id])
            if cal_reward > self.best_area[id]:
                self.best_area[id] = cal_reward 
                area_reward[id] = self.best_area[id]
            else:
                # no point is given if the drone does not move to new area
                area_reward[id] = 0
        print("area_reward_best:", area_reward)
        # decide if episode should be terminated
        done = False

        # fly below min height or above max height
        out_range = [False, False, False]
        out_small_range = [False, False, False]
        for id, drone in enumerate(droneList):
            if drone_pos[id].x_val > max_small_x or drone_pos[id].x_val < min_small_x or drone_pos[id].y_val > max_small_y or drone_pos[id].y_val < min_small_y: 
                out_small_range[id] = True
            print("drone_pos[id].z_val: ", drone_pos[id].z_val)
            if drone_pos[id].z_val > min_height or drone_pos[id].z_val < max_height or drone_pos[id].x_val > max_x or drone_pos[id].x_val < min_x or drone_pos[id].y_val > max_y or drone_pos[id].y_val < min_y: 
                out_range[id] = True

        print("has_collided: ", has_collided)
        print("out_range: ", out_range)
        print("out_small_range: ", out_small_range)

        # done if 2 targets are found
        done = any(has_collided) or any(out_range) or sum(success) == target_num    

        # compute reward
        reward = self.compute_reward(exist_reward, focus_reward, area_reward, spread_reward, dsensor_reward, success, out_small_range, done)

        # log info
        loginfo = []
        for id, drone in enumerate(droneList):
            info = {}
            info['Z'] = drone_pos[id].z_val
            if landed[id]:
                info['status'] = 'landed'
            elif has_collided[id]:
                info['status'] = 'collision'
            elif out_range[id]:
                info['status'] = 'dead'
            elif success[id] == True:
                info['status'] = 'success'   
            elif exist_reward[id] == 'found':
                info['status'] = 'found_out'
            elif any(dsensor_reward):
                info['status'] = 'dsensor_close'     
            elif exist_reward[id] == 'miss':
                info['status'] = 'miss'
            else:
                info['status'] = 'none'
            loginfo.append(info)

        # convert responses from nested list into list. Used all of the images captured by drones.
        obs_responses = self.nested_list_to_list(responses)  

        observation = [obs_responses, drone_dist]
        return observation, reward, done, loginfo

    def stabilize(self, drone):
        #print("stabilize")
        time.sleep(0.1)
        self.dc.moveDroneBySelfFrame(drone, [0,0,-1], 0.125)
        time.sleep(0.1)
        self.dc.moveDroneBySelfFrame(drone, [0,0,1], 0.1)

    def check_focus(self, bbox, image):
        image_h, image_w, _ = image.shape
        xmin, ymin, xmax, ymax = self.dc.convert_bbox(bbox[2][0], bbox[2][1], bbox[2][2], bbox[2][3])
        c_x = bbox[2][0]
        c_y = bbox[2][1]

        img_cen_x = image_w / 2
        img_cen_y = image_h / 2

        # Check if the center of the detection box is within the bounding box 'fbbox' 
        fbbox = {
            'xmin': int(img_cen_x - (image_w * focus_size / 2)), # Xmin
            'xmax': int(img_cen_x + (image_w * focus_size / 2)), # Xmax
            'ymin': int(img_cen_y - (image_h * focus_size / 2)), # Ymin
            'ymax': int(img_cen_y + (image_h * focus_size / 2))  # Ymax
        }

        if (xmin > fbbox['xmin'] and xmax < fbbox['xmax']) and (ymin > fbbox['ymin'] and ymax < fbbox['ymax']):
            status = 'in'
        else:
            status = 'out'            
        return status

    def check_size(self, bbox, image):
        image_h, image_w, _ = image.shape
        xmin, ymin, xmax, ymax = self.dc.convert_bbox(bbox[2][0], bbox[2][1], bbox[2][2], bbox[2][3])
        y_delta = (ymax - ymin)/image_h
        x_delta = (xmax - xmin)/image_w
        # if the bbox size is larger than certain size, then it will be in 'large' status, otherwise in 'small' status.
        if y_delta > 0.8 and x_delta > 0.25:
            status = 'large'
        else:
            status = 'small'
        return status

    # assign rewards
    def compute_reward(self, exist_reward, focus_reward, area_reward, spread_reward, dsensor_reward, success, out_small_range, done):
        reward = [None] * len(droneList)
        for id, drone in enumerate(droneList):         
            #img = responses[id]
            exist_status = exist_reward[id]
            focus_status = focus_reward[id]
            #size_status = size_reward[id]
            area_rwd_pt = area_reward[id]
            
            # if distance sensor is too near any obstacle, give penalty
            # if any(dsensor_reward):
            #     reward[id] = config.reward['dsensor_close']
            #     continue

            # Assign reward value based on status
            if done:
                if sum(success) == target_num:
                    reward[id] = config.reward['success']
                else:
                    reward[id] = config.reward['dead']
            elif exist_status == 'miss':
                reward[id] = config.reward['miss']
            elif exist_status == 'found' and focus_status == 'in':
                reward[id] = config.reward['in']
            elif exist_status == 'found' and focus_status == 'out':
                reward[id] = config.reward['out']
            else:
                reward[id] = config.reward['none']

            # team rewards
            reward[id] += area_rwd_pt

            # if drones are not spread enough, give penalty
            if spread_reward == 'near':
                reward[id] += config.reward['near']

            # if distance sensor is too near any obstacle, give penalty
            if any(dsensor_reward):
                reward[id] += config.reward['dsensor_close']

            # if drone is near to the boundary 
            if out_small_range[id] == True:
                reward[id] += config.reward['out_small']


            # Append GPS rewards
            # if img_status != 'dead':            
            #     gps = gps_dist[droneidx]
            #     if gps > 9 or gps < 2.3:
            #         reward[id] = reward[id] + config.reward['dead']
            #     else:
            #         reward[id] = reward[id] + config.reward['forward']
        return reward
    
    
    def disconnect(self):
        self.dc.shutdown_AirSim()
        print('Disconnected.')