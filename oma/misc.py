import math

def downloadURL_hog(fam):
    return '/All/HOGs/{0:04d}/HOG{1:07d}.orthoxml'.format(
            int(math.ceil(fam/500.0)), fam)
