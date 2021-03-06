import math
import numpy as np
import config

area_width = 52 * 2  # in meter
cell_width = 0.5  # in meter
# projected_dist is the xy plane distance between drone and the center of covered area 
proj_dist = 11  # in meter
covered_length = 8 # in meter
pad_size = 45 # in grid cells
#covered_reward_pt = 0.01
cell_value = 1
covered_reward_pt = config.reward['area']

length = int(area_width / cell_width) # in grid cells
grid = np.zeros(shape=(length, length))
grid_pad = np.pad(grid, pad_size, mode='constant', constant_values=-1).astype(float)

# Display the cells
#np.savetxt("grid.csv", grid_pad, delimiter=",", fmt='%s')

def reset_grid():
    global grid_pad
    grid_pad = np.pad(grid, pad_size, mode='constant', constant_values=-1).astype(float)
    record()

def add_data(i, j, data):
    #print("i:", i)
    #print("j:", j)
    # if the grid is -1, do not fill in any value
    if grid_pad[i][j] != -1:
        grid_pad[i][j] = data 

        
def record():
    np.savetxt("grid.csv", grid_pad, delimiter=",", fmt='%s')

def discretize(f_pos):
    i = int(length - (f_pos[0] - (-area_width/2))//cell_width) + pad_size - 1 
    j = int((f_pos[1] - (-area_width/2))//cell_width) + pad_size - 1
    return i, j

def calculate_reward():
    # get the area reward without padding cells
    grid_center = grid_pad[pad_size:length-pad_size, pad_size:length-pad_size]
    covered_reward = np.sum(grid_center)
    total_reward = length * length 
    reward_pt = (covered_reward/total_reward) * covered_reward_pt  
    #covered_reward = round(covered_reward, 2)
    return reward_pt

def deg_to_rad(deg):
    return deg*math.pi/180

def rad_to_deg(rad):
    return rad*180/math.pi

# main function 
def covered_area(pos_x, pos_y, yaw, camList, cam_shifted_angle):
    # Note: calculated angles are in radians.
    
    # separation angle between camera in drone
    cam_sep_angle = deg_to_rad(360/len(camList))

    # shifted yaw angles of the cameras 
    angle_shifted = deg_to_rad(cam_shifted_angle)
    #print("angle_shifted: ", angle_shifted)
    # loop for every camera in every drone.
    for i in range(len(camList)):
        #print("calculating covered area.")
        cam_yaw = yaw + i*cam_sep_angle + angle_shifted
        #print("cam_yaw: ", rad_to_deg(cam_yaw))
        pos = np.array([pos_x, pos_y])
        trans = np.array([proj_dist* math.cos(cam_yaw), proj_dist* math.sin(cam_yaw)])
        f_pos = np.sum([pos, trans], axis=0)
        #print("pos: ", pos)
        #print("trans: ", trans)
        #print("f_pos: ", f_pos)

        # # convert f_pos into grid coordinate, and display the cells in .csv file
        i1, j1 = discretize(f_pos)
        #add_data(i1, j1, 1)

        i2, j2 = discretize(pos)
        #add_data(i2, j2, 0)

        # spread the grid for the covered area
        spread_size = int((covered_length/2)// cell_width)
        #print("spread_size: ", spread_size)
        spread_i = [i + i1 for i in range(-spread_size, spread_size+1)]
        spread_j = [j + j1 for j in range(-spread_size, spread_size+1)]
        #print("spread_i: ", spread_i)
        #print("spread_j: ", spread_j)
        for i in spread_i:
            for j in spread_j:
                add_data(i, j, cell_value)

    record()
    #print("Done")

    # get total summation for the reward
    reward_pt = calculate_reward()
    #print("reward_pt: ", reward_pt)
    reward = round(reward_pt, 2)
    return reward
    