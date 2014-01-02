# Quick script to generate LUT files for the analog daq program

import numpy as np
import sys

def myfunc(x):
    val = (5.0*(x/65535.0))*10.0
    #p = 10.0**(val - 6.0)
    return(val)
    #return(p)

# Thermistors
def temp(x):
    vol = 5.0*(x/65535.0)
    f = -40.5433*vol + 216.4608
    c = (f - 32.0)*(5.0/9.0)

    return(c)


def main(fname):
    z = np.array(range(65536))
    y = np.zeros(65536)
    for x in z:
        #y[x] = myfunc(x)
        y[x] = temp(x)

    print(y)

    np.savetxt(fname, y)
        

if __name__ == '__main__':
    if (len(sys.argv) > 1):
        main(sys.argv[1])
    else:
        print("No name!")
