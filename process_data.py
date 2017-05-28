import os
import numpy as np
from scipy import misc
import matplotlib.pyplot as plt
import glob
import natsort

classes = []
examples = []

iLIDS_dir = '/home/machine/Downloads/i-LIDS-VID/sequences/'
for f in range(1,320):
    dir1_id = iLIDS_dir+'cam1/person'+np.str(f).zfill(3)
    #dir2_id = iLIDS_dir+'cam2/person'+np.str(f).zfill(3)
    files1 = natsort.natsorted(glob.glob(dir1_id+'/*.png'))
    #files2 = natsort.natsorted(glob.glob(dir2_id+'/*.png'))
    #files = files1+files2
    files = files1
    
    for i in range(len(files)):
        cur_pic = misc.imread(files[i])
        cur_pic = np.float32(cur_pic)/255

        if i == 0:
            examples = [cur_pic]
            classes.append(examples)
        else:
            examples.append(cur_pic)
            
np.save('data',np.asarray(classes))
print len(classes)
print len(classes[0])
print len(classes[0][0])
print len(classes[0][0][0])
print len(classes[0][0][0][0])
print len(classes[1])
print len(classes[1][0])
print len(classes[1][0][0])
print len(classes[1][0][0][0])