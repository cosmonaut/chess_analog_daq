import sys
import struct
import os
import datetime
import numpy as np
import pyfits as pf

from PyQt4 import QtGui, Qt

def main(fname, conf_name):
    f = open(fname, 'rb')

    statinfo = os.stat(fname)
    fsize = statinfo.st_size

    if ((fsize % 64) != 0):
        print("Warning: file may be corrupt...")

    if (fsize < 64):
        f.close()
        raise Exception("File not large enough to parse...")

    # config stuff
    lut_file_map = dict()
    lut_map = dict()
    loaded_lut_map = dict()
    chname_map = dict()
    
    print("Loading config file: %s" % conf_name)
    s = Qt.QSettings(conf_name, Qt.QSettings.NativeFormat, None)

    settings_map = dict()

    # Load settings
    if (len(s.childKeys()) != 32):
        print("BAD CONFIG FILE")
    else:
        # load settings!
        for k in s.childKeys():
            settings_map[str(k)] = s.value(k).toPyObject()[0]

    # Load LUT file names
    for k in settings_map.keys():
        lut_file_map[int(k)] = settings_map[k]['lut_file']
        chname_map[int(k)] = settings_map[k]['chname']

    # Default LUT
    LUT = []
    for i in range(65536):
        LUT.append([i, 5.0*(i/65535.0)])
    LUT = np.array(LUT)
    dLUT = dict((key, value) for (key, value) in LUT)

    # Process LUT files
    print("Processing LUTs")
    for k in lut_file_map.keys():
        if (lut_file_map[k]):
            if os.path.exists(lut_file_map[k]):
                print(lut_file_map[k])
                # This prevents reloading identical LUTs
                if (lut_file_map[k] in loaded_lut_map):
                    lut_map[int(k)] = lut_map[loaded_lut_map[lut_file_map[k]]]
                else:
                    arr = np.genfromtxt(lut_file_map[k])
                    if (len(arr) == 65536):
                        #print(arr)
                        d = dict()
                        for n, val in enumerate(arr):
                            d[n] = val
                        lut_map[int(k)] = d
                        loaded_lut_map[lut_file_map[k]] = int(k)
                        #print(self.lut_map)
                    else:
                        print("WARNING: malformed LUT, using default LUT: %s" % lut_file_map[k])
                        # Use default LUT
                        lut_map[int(k)] = dLUT
            else:
                print("LUT FILE LOAD ERROR! %s" % lut_file_map[k])

        else:
            # Load default LUT
            lut_map[int(k)] = dLUT


    # Load file header
    header = f.read(64)
    scan_freq = struct.unpack('H', header[0:2])[0]
    print("SCAN FREQ: %i" % scan_freq)

    # Datetime from header
    year = struct.unpack('H', header[2:4])[0]
    month = struct.unpack('H', header[4:6])[0]
    day = struct.unpack('H', header[6:8])[0]
    hour = struct.unpack('H', header[8:10])[0]
    minute = struct.unpack('H', header[10:12])[0]
    second = struct.unpack('H', header[12:14])[0]
    millisecond = struct.unpack('H', header[14:16])[0]

    date_obs = datetime.datetime(year, month, day, hour, minute, second, int(round(millisecond*1000.0)))

    
    # Calculate number of rows for data...
    # 64 byte header...
    # 64 bytes per row.
    arr_size = (fsize - 64)/64.0
    #print("ARR SIZE: %f" % arr_size)
    data_wad = dict()
    data_wad['t'] = np.zeros(arr_size)
    for i in range(32):
        data_wad[i] = np.zeros(arr_size)

    sampling_time = 0.0
    row_num = 0
    while(1):
        dat = f.read(64)
        if (len(dat) == 64):
            # Parse a row of data
            data_tup = struct.unpack('32H', dat)
            for n, d in enumerate(data_tup):
                data_wad[n][row_num] = lut_map[n][d]
                #l.append(lut_map[n][d])

            data_wad['t'][row_num] = sampling_time

            # increment time and row number...
            sampling_time += 1.0/float(scan_freq)
            row_num += 1
            
        else:
            # No more data in the file...
            print("dat: %i" % len(dat))
            #print(dat)
            print("Read %i bytes" % f.tell())

            break


    if (f.tell() != fsize):
        print("Read bytes mismatch file size")
            
    f.close()

    fits_name = os.path.splitext(fname)
    fits_name = fits_name[0] + '.fits'

    save_fits(fits_name, data_wad, chname_map, date_obs)
    
    return(0)


def save_fits(fits_name, data_wad, col_names, dt):
    # Prep column strings
    col_strings = []
    for i in range(32):
        col_strings.append(str(i) + " " + col_names[i])

    col_list = []
    col_list.append(pf.Column(name = "Time", format = 'D', unit = "second", array = data_wad['t']))
    for i in range(32):
        col_list.append(pf.Column(name = col_strings[i], format = 'D', array = data_wad[i]))

    # for c in col_list:
    #     print(c.name)

    tbhdu = pf.new_table(col_list)
    if (fits_name.endswith(".fits")):
        pass
    else:
        fits_name = fits_name + ".fits"

    date_obs_str = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")

    tbhdu.header.update('DATE-OBS', date_obs_str)

    tbhdu.writeto(fits_name)

if __name__ == '__main__':
    if (len(sys.argv) < 3):
        raise Exception("Usage: %s <log file> <conf_file>" % sys.argv[0])

    print(sys.argv[2])

    main(sys.argv[1], sys.argv[2])
        
