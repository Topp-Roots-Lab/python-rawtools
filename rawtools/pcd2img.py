'''
Created on Feb 25, 2020

@author: njiang
'''

import os, argparse
import numpy as np
from imageio.core.functions import imwrite

def options():
     
    parser = argparse.ArgumentParser(description='Generate binary slices from .out point cloud',formatter_class=argparse.ArgumentDefaultsHelpFormatter)
     
    parser.add_argument('-i', "--input_folder", help="directory of .out files", required=True)
     
    args = parser.parse_args()
 
    return args
 
args = options()

folder = args.input_folder

for fname in [out for out in os.listdir(folder) if out.endswith(".out")]:
    output_dir = os.path.join(folder, os.path.splitext(os.path.basename(fname))[0]);
    
    indices = np.genfromtxt(os.path.join(folder, fname), delimiter = ' ', skip_header = 2)
    width, height, depth = np.amax(indices, axis = 0)

    volume = np.zeros((int(width+1), int(height+1), int(depth+1)), dtype = np.uint8)
    a = np.rint(indices).astype(np.int32)
    volume[a[:, 0], a[:, 1], a[:, 2]] = 255

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        for i in range(0, int(depth+1)):
            imwrite(output_dir+('/%04d.png'%i), volume[:, :, i].astype(np.uint8))


