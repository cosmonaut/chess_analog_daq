import sys
import os
import select
import collections
import math
import struct
import re
import numpy as np

import comedi as c

from PyQt4 import QtGui, QtCore

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas


COMEDI_PROC_F = "/proc/comedi"
PCI_6033E_PATTERN = '\s*(\d):\s*ni_pcimio\s*pci-6033e\s*\d\d'
DEVICE = "/dev/comedi2"
SUBDEVICE = 0
# Buffer for reading the file device.
#BUF_SIZE = 10000
BUF_SIZE = 10000
# Scans of all 32 channels per second
SCAN_FREQ = 100
# 2 bytes per word
WORD_SIZE = 2
# Channel we want to use for 0-5 V
CHAN_RANGE = 8
NUM_CHANNELS = 32
# Size of reads from comedi file device
#FD_BUF_SIZE = 65536
FD_BUF_SIZE = 262144


class BlitPlot(FigureCanvas):
    def __init__(self, parent = None):
        #super(BlitPlot, self).__init__()
        print("Init blitplot")
        self.fig = Figure()
        FigureCanvas.__init__(self, self.fig)
        self.canvas = self.fig.canvas

        self.ax_list = []
        self.ax_list.append(self.fig.add_subplot(511))
        self.ax_list.append(self.fig.add_subplot(512))
        self.ax_list.append(self.fig.add_subplot(513))
        self.ax_list.append(self.fig.add_subplot(514))
        self.ax_list.append(self.fig.add_subplot(515))
        
        #self.axes = self.fig.add_subplot(211)
        #self.axes2 = self.fig.add_subplot(212)
        #self.axes.hold(False)

        #self.axes.plot([1,2,3],[1,2,3])
        for n in range(len(self.ax_list)):
        
            self.ax_list[n].xaxis.set_animated(True)
            self.ax_list[n].yaxis.set_animated(True)

            self.ax_list[n].set_xlim([1000.0/SCAN_FREQ, 0])
            self.ax_list[n].set_ylim([-0.4, 5.4])
            #self.ax_list[n].set_ylim([0, 70000])

            self.ax_list[n].grid(True)
            self.ax_list[n].xaxis.set_ticks_position('none')
        


            self.ax_list[n].set_xlabel("Time")
            self.ax_list[n].set_ylabel("Voltage")

        self.line_map = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0, 6:0, 7:0,
                         8:1, 9:1, 10:1, 11:1, 12:1, 13:1, 14:1,
                         15:2, 16:2, 17:2, 18:2, 19:2, 20:2, 21:2,
                         22:3, 23:3, 24:3, 25:3, 26:3, 27:3, 28:3,
                         29:4, 30:4, 31:4}

        #print(self.line_map.items())
        self.ax_map = {v:k for k,v in self.line_map.items()}
        #print(self.ax_map)
            
        self.line_list = []
        for i in range(32):
            #print(self.line_map[i])
            self.line_list.append((self.ax_list[self.line_map[i]].plot([], [], animated = True))[0])

        self.fig.subplots_adjust(left = 0.1, right = 0.95, top = 0.95, bottom = 0.05)
        #self.fig.tight_layout()
        # self.v_line, = self.ax_list[0].plot([], [], animated = True)
        # self.i_line, = self.ax_list[1].plot([], [], animated = True)
        # self.vac_line, = self.ax_list[2].plot([], [], animated = True)
        

        
        # self.axes.xaxis.set_animated(True)
        # self.axes.yaxis.set_animated(True)

        # self.axes.set_xlim([1000.0/SCAN_FREQ, 0])
        # self.axes.set_ylim([0, 66000])

        # self.axes.grid(True)
        
        # self.v_line, = self.axes.plot([], [], animated = True)

        # self.axes.set_xlabel("Time")
        # self.axes.set_ylabel("Voltage")
        # self.axes.set_title("ZOMGBBQ")


        
        self.lastx = 0
                        
        # Clean background
        self.clean_bg = self.canvas.copy_from_bbox(self.fig.bbox)
        #self.background = self.canvas.copy_from_bbox(self.get_bg_bbox(self.axes))
        self.bg_list = []
        for n in range(len(self.ax_list)):
            self.bg_list.append(self.canvas.copy_from_bbox(self.get_bg_bbox(self.ax_list[n])))

        #self.old_size = self.axes.bbox.width, self.axes.bbox.height
        self.canvas.draw()
        self.draw()
        self.do_redraw = True

        self.fifo_size = BUF_SIZE
        self.totx = 0

        LUT = []
        for i in range(65536):
            LUT.append([i, 5.0*(i/65535.0)])
        LUT = np.array(LUT)
        self.dLUT = dict((key, value) for (key, value) in LUT)
        #LUT = np.array([range(65536), [0]*65536])
        #LUT_y = np.zeros(65536)
        #LUT = np.reshape(LUT, (65536, 2))
        # for i in range(65536):
        #     LUT[i, 1] = 5.0*(float(i)/65536.0)

        #print(dLUT)

        
        
        self.setParent(parent)
        print("finish init blitplot")

    def redraw(self):
        self.do_redraw = True
        
    # Get the bounding box
    def get_bg_bbox(self, axe):
        # just pad x0 by three....
        return axe.bbox.padded(-3)

    def del_px_data(self, d_x, ax):
        xpx_old, ypx_old = ax.transData.transform((0, 0))
        xpx_new, ypx_new = ax.transData.transform((d_x, 0))

        return(xpx_new - xpx_old)

    # Get delta x from pixel data
    def get_dx_data(self, dx_pixel, ax):
        tp = ax.transData.inverted().transform_point
        x0, y0 = tp((0, 0))
        x1, y1 = tp((dx_pixel, 0))
        return(x1 - x0)

        
    def clear_plot(self):
        for n in range(len(self.ax_list)):
            self.ax_list[n].clear()
            self.ax_list[n].grid(True)
            self.bg_list[n] = self.canvas.copy_from_bbox(self.get_bg_bbox(self.ax_list[n]))

        self.canvas.draw()
        self.clean_bg = self.canvas.copy_from_bbox(self.fig.bbox)
        #self.background = self.canvas.copy_from_bbox(self.get_bg_bbox(self.axes))
        self.do_redraw = False
        print("clear")
        
        
    def update_plots(self, x, y):
        if (len(x) == 0):
            return
        
        if (self.do_redraw):
            for n in range(len(self.ax_list)):
                self.ax_list[n].clear()
                self.ax_list[n].grid(True)
                
            self.canvas.draw()
            self.clean_bg = self.canvas.copy_from_bbox(self.fig.bbox)
            for n in range(len(self.bg_list)):
                self.bg_list[n] = self.canvas.copy_from_bbox(self.get_bg_bbox(self.ax_list[n]))
            #self.background = self.canvas.copy_from_bbox(self.get_bg_bbox(self.axes))
            self.do_redraw = False
            print("REDRAW")
            #self.lastx = x[0]

            # self.axes.clear()
            # self.axes.grid(True)
            # self.canvas.draw()
            # self.clean_bg = self.canvas.copy_from_bbox(self.fig.bbox)
            # self.background = self.canvas.copy_from_bbox(self.get_bg_bbox(self.axes))
            # self.do_redraw = False

        #print(x, y)


        # for n in range(len(self.ax_list)):
        #    self.ax_list[n].set_xlim([x[-1] - self.fifo_size/SCAN_FREQ - 1, x[-1] + 1])
        
            
        #self.axes.set_xlim([x[-1] - self.fifo_size/SCAN_FREQ - 1, x[-1] + 1])
        # Restore the blank background
        self.canvas.restore_region(self.clean_bg)

        xarr = np.array(x)

        lastx_ind = np.where(xarr > self.lastx)
        #lastx_ind = itertools.islice(self.lastx

        lastx_ind = lastx_ind[0]
                
        # Offset in time
        x_offset = abs(xarr[-1] - self.lastx)



        # analog_arr = np.array(y[0])
        # analog_arr2 = np.array(y[18])
        # analog_arr = (analog_arr/65536.0)*5.0
        # analog_arr2 = (analog_arr2/65536.0)*5.0

            
        #xtest = abs((xarr[-1] + 1) - (xarr[-1] - self.fifo_size/SCAN_FREQ - 1))
        #pxtest = self.del_px_data(xtest, self.ax_list[0])


        # Find the equivalent offset in display pixels
        #pixel_offset = self.del_px_data(x_offset)
        #dx_pixel = np.floor(pixel_offset)

        
        #for n in range(len(self.ax_list)):
        #    self.ax_list[n].set_xlim([xarr[-1] - self.fifo_size/SCAN_FREQ - 1, xarr[-1] + 1])


        px_offset = self.del_px_data(x_offset, self.ax_list[0])
        dx_pixel = np.floor(px_offset)
        x_motion_adj = self.get_dx_data(dx_pixel, self.ax_list[0])
        self.lastx += x_motion_adj

        #print(self.lastx, xarr[-1])

        # Compute and redraw saved background (moved over).
        for n in range(len(self.bg_list)):
            #print(x_offset)
            # Find the equivalent offset in display pixels
            # pixel_offset = self.del_px_data(x_offset, self.ax_list[n])
            # dx_pixel = np.floor(pixel_offset)

            # xtest = self.get_dx_data(dx_pixel, self.ax_list[n])

            # if (n%2 == 0):
            #     self.totx += xtest
            #     print("Total X movement: %f" % self.totx)

            #print(dx_pixel, xtest)
            #print(xarr[-1], y[0][-1])
            #self.ax_list[n].set_xlim([self.lastx + xtest - self.fifo_size/SCAN_FREQ, self.lastx + xtest + 1])
            #self.ax_list[n].set_xlim([self.lastx + xtest - 4, self.lastx + xtest + 1])
            #self.ax_list[n].set_xlim([self.lastx + x_offset - 4, self.lastx + x_offset + 1])

            self.ax_list[n].set_xlim([self.lastx - self.fifo_size/SCAN_FREQ, self.lastx + 1])
            
            #print("asdf", x_offset, dx_pixel)
            #print(dx_pixel, pixel_offset)
            
            x1, y1, x2, y2 = self.bg_list[n].get_extents()
            self.canvas.restore_region(self.bg_list[n],
                                       bbox = (x1 + dx_pixel, y1, x2, y2),
                                       xy = (x1 - dx_pixel, y1))



        for i in range(32):
            self.line_list[i].set_xdata(xarr)
            self.line_list[i].set_ydata(y[i])
            #print(len(xarr), len(y[i]))
            self.ax_list[self.line_map[i]].draw_artist(self.line_list[i])

        #self.v_line.set_xdata(xarr[lastx_ind])
        #self.v_line.set_ydata(analog_arr[lastx_ind])
        # self.ax_list[0].draw_artist(self.v_line)

        # self.i_line.set_xdata(xarr[lastx_ind])
        # self.i_line.set_ydata(analog_arr2[lastx_ind])
        # self.ax_list[1].draw_artist(self.i_line)

        # self.vac_line.set_xdata(xarr[lastx_ind])
        # self.vac_line.set_ydata(analog_arr2[lastx_ind])
        # self.ax_list[2].draw_artist(self.vac_line)

        # x1, y1, x2, y2 = self.background.get_extents()
        # self.canvas.restore_region(self.background,
        #                            bbox = (x1 + dx_pixel, y1, x2, y2),
        #                            xy = (x1 - dx_pixel, y1))

        # self.v_line.set_xdata(xarr[lastx_ind])
        # self.v_line.set_ydata(analog_arr[lastx_ind])
        # self.axes.draw_artist(self.v_line)

        
        # self.my_line2.set_xdata(xarr[lastx_ind])
        # self.my_line2.set_ydata(analog_arr2[lastx_ind])
        # self.a.draw_artist(self.my_line2)

        #for n, bg in enumerate(self.bg_list):
        for n in range(len(self.bg_list)):
            self.bg_list[n] = self.canvas.copy_from_bbox(self.get_bg_bbox(self.ax_list[n]))
        #self.background = self.canvas.copy_from_bbox(self.get_bg_bbox(self.axes))

        for n in range(len(self.ax_list)):
            # Draw the axes (and grids if applicable)
            self.ax_list[n].draw_artist(self.ax_list[n].xaxis)
            self.ax_list[n].draw_artist(self.ax_list[n].yaxis)
            #ax.draw_artist(ax.yaxis)
            #self.canvas.blit(ax.clipbox)

        # Draw the axes (and grids if applicable)
        #self.axes.draw_artist(self.axes.xaxis)
        #self.axes.draw_artist(self.axes.yaxis)

        #self.canvas.blit(self.ax_list[0].bbox)
        #self.canvas.blit(self.ax_list[1].bbox)
        #self.canvas.blit(self.ax_list[0].clipbox)
        self.canvas.blit(self.fig.bbox)
        
        #self.lastx = xarr[-1]

        

class AnalogDAQWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle("CHESS Analog DAQ")

        self.plot = BlitPlot()
        self.plot.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)

        self.daq = AnalogCard()

        self.main_widget = QtGui.QWidget(self)

        self.table = QtGui.QTableWidget(self)
        #self.table.setFlags(self.table.flags() ^ QtCore.ItemIsEditable)
        self.table.setRowCount(32)
        self.table.setColumnCount(2)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setStyleSheet("QTableWidget::item { border: 0px; padding: 0px }")

        
        for r in range(self.table.rowCount()):
            self.table.setItem(r, 0, QtGui.QTableWidgetItem("Channel %d" % r))
            #temp_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.table.item(r, 0).setFlags(QtCore.Qt.ItemIsEnabled)

            self.table.setItem(r, 1, QtGui.QTableWidgetItem("0.0"))
            self.table.item(r, 1).setFlags(QtCore.Qt.ItemIsEnabled)
            
            # for c in range(self.table.columnCount()):
            #     #print("ASDF")
            #     #print(self.table.item.flags())
            #     #self.table.item(r, c).setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            #     print(r, c)
            #     print(self.table.item(r, c))


        self.table.resizeRowsToContents()
        self.table.setSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Minimum)
        #self.table.setMaximumWidth(222)
        w = self.table.columnWidth(0) + self.table.columnWidth(1)
        #print(w)
        self.table.setMinimumWidth(w+10)
        self.table.setMaximumWidth(w+10)
        h = 0
        for i in range(32):
            h += self.table.rowHeight(i)

        #print(h)
        self.table.setMinimumHeight(h + 10)
                
        self.acq_button = QtGui.QPushButton("Acquire", self)
        self.acq_button.setCheckable(True)

        self.acq_button.clicked[bool].connect(self.acquire)

        self.acq_timer = QtCore.QTimer(self)
        self.acq_timer.setSingleShot(False)
        self.acq_timer.setInterval(0)
        self.acq_timer.timeout.connect(self.daq.get_data)

        self.num_disp_timer = QtCore.QTimer(self)
        self.num_disp_timer.setSingleShot(False)
        self.num_disp_timer.setInterval(1000)
        self.num_disp_timer.timeout.connect(self.update_numbers)

        self.plot_timer = QtCore.QTimer(self)
        self.plot_timer.setSingleShot(False)
        self.plot_timer.setInterval(32)
        self.plot_timer.timeout.connect(self.update_plots)
        
        vl = QtGui.QVBoxLayout(self.main_widget)
        hl = QtGui.QHBoxLayout()
        hl.setSizeConstraint(QtGui.QLayout.SetMinimumSize)
        hl.addWidget(self.plot)
        hl.addWidget(self.table)
        
        #vl.addWidget(self.plot)
        #vl.addWidget(self.table)
        vl.addLayout(hl)
        vl.addWidget(self.acq_button)
        
        self.main_widget.setFocus()
        self.setCentralWidget(self.main_widget)

        LUT = []
        for i in range(65536):
            LUT.append([i, 5.0*(i/65535.0)])
        LUT = np.array(LUT)
        self.dLUT = dict((key, value) for (key, value) in LUT)

                        
        self.statusBar().showMessage("CHESS Analog DAQ Initialized")

    def acquire(self, pressed):
        if pressed:
            self.daq.start()
            self.acq_timer.start()
            self.num_disp_timer.start()
            self.plot.lastx = 0
            self.plot.redraw()
            self.plot_timer.start()
            self.acq_button.setText("Halt")
        else:
            self.num_disp_timer.stop()
            self.plot_timer.stop()
            self.acq_timer.stop()
            self.daq.stop()
            self.acq_button.setText("Acquire")

    def update_numbers(self):
        #x, y = self.daq.get_batch()
        x, y = self.daq.get_last()
        for r in range(self.table.rowCount()):
            #self.table.item(r, 1).setText(str(5.0*y[r][-1]/65535.0))
            #self.table.item(r, 1).setText(str(self.dLUT[y[r]]).format("%0.2f"))
            self.table.item(r, 1).setText(("%0.2f" % self.dLUT[y[r]]))
            #self.table.item(r, 1).setText(("%0.2f" % y[r]))


    def update_plots(self):
        #x, y = self.daq.get_batch()
        x, y = self.daq.get_new()
        for row in y:
            for n in range(len(row)):
                row[n] = self.dLUT[row[n]]
        self.plot.update_plots(x, y)

    def resizeEvent(self, evt = None):
        #print("RESIZE!")
        self.plot.redraw()
        
    def closeEvent(self, ce):
        # Close DAQ card
        self.daq.stop()
        self.daq.close()
        print("Cleaned up...")

# Handle all DAQ card functionality
class AnalogCard:
    def __init__(self):
        # Find comedi analog device number
        try:
            with open(COMEDI_PROC_F) as f:
                #print(f)
                for line in f.readlines():
                    m = re.match(PCI_6033E_PATTERN, line)
                    if m:
                        print(m.group())
                        dev_number = m.groups()[0]
                        dev_fname = "/dev/comedi" + dev_number
        except IOError:
            print("Could not find file: %s" % COMEDI_PROC_F)

        if (f):
            f.close()
        
        #self.dev = c.comedi_open(DEVICE)
        self.dev = c.comedi_open(dev_fname)
        if not(self.dev):
            print("Unable to open comedi device...")
            
        ret = c.comedi_lock(self.dev, SUBDEVICE)
        if (ret < 0):
            print("Could not lock comedi device")

        bs = c.comedi_get_buffer_size(self.dev, SUBDEVICE)
        ms = c.comedi_get_max_buffer_size(self.dev, SUBDEVICE)
        print("buf size: %f" % bs)
        print("max buf size: %f" % ms)
        if (ms > 0):
            ms = c.comedi_set_buffer_size(self.dev, SUBDEVICE, ms)
            print("Final analog device buffer size: %i" % ms)
            
        # get a file-descriptor for use later
        self.fd = c.comedi_fileno(self.dev)
        if (self.fd <= 0): 
            print("Error obtaining Comedi device file descriptor")
            #c.comedi_close(self.dev)
        
        # Channel range (0-5V)
        if (c.comedi_range_is_chan_specific(self.dev, SUBDEVICE) != 0):
            print("Comedi range is channel specific!")

        self.comedi_range = c.comedi_get_range(self.dev, SUBDEVICE, 0, CHAN_RANGE)
        self.comedi_maxdata = c.comedi_get_maxdata(self.dev, SUBDEVICE, 0)
        
        board_name = c.comedi_get_board_name(self.dev)
        if (board_name != "pci-6033e"):
            print("Opened wrong device!")

        # Prepare channels, gains, refs
        self.comedi_num_chans = NUM_CHANNELS
        chans = range(self.comedi_num_chans)
        gains = [CHAN_RANGE]*self.comedi_num_chans
        aref = [c.AREF_GROUND]*self.comedi_num_chans

        chan_list = c.chanlist(self.comedi_num_chans)

        # Configure all the channels!
        for i in range(self.comedi_num_chans):
            chan_list[i] = c.cr_pack(chans[i], gains[i], aref[i])

        # The comedi command
        self.cmd = c.comedi_cmd_struct()

        # 1.0e9 because this number is in nanoseconds for some reason
        period = int(1.0e9/float(SCAN_FREQ))

        # Init cmd
        ret = c.comedi_get_cmd_generic_timed(self.dev, SUBDEVICE, self.cmd, self.comedi_num_chans, period)
        if (ret):
            print("Could not initiate command")

        # Populate command 
        self.cmd.chanlist = chan_list
        self.cmd.chanlist_len = self.comedi_num_chans
        self.cmd.scan_end_arg = self.comedi_num_chans
        self.cmd.stop_src = c.TRIG_NONE
        self.cmd.stop_arg = 0

        print("real timing: %d ns" % self.cmd.convert_arg)
        print("Real scan freq: %d Hz" % (1.0/(float(self.cmd.convert_arg)*32.0*1.0e-9)))
        #print("period: %d ns" % period)
    
        print_cmd(self.cmd)

        # Test command out.
        ret = c.comedi_command_test(self.dev, self.cmd)
        if (ret < 0):
            print("Comedi command test failed!")


        self.fifo_size = BUF_SIZE
        # String buffer for comedi data acq
        self.data_buf = ""
        self.analog_data = []
        for i in range(NUM_CHANNELS):
            self.analog_data.append(collections.deque([], self.fifo_size))
        self.x = collections.deque([], self.fifo_size)

        self.last_x = 0

        self.last_analog = [0]*32

        # self.analog_data.append(collections.deque(self.fifo_size*[0], self.fifo_size), self.fifo_size)
        # self.x = collections.deque(self.fifo_size*[0], self.fifo_size)

            
        print("Init analog card")

    # Acquisition function that should be repeatedly called to put
    # hardware data in the queue.
    def get_data(self):
        # Run the command
        # ret = c.comedi_command(self.dev, self.cmd)
        # if (ret != 0):
        #     self.warn_dialog("PCI-6033E cannot collect data! Error: %d" % ret)
        #     print(c.comedi_strerror(c.comedi_errno()))
        #     return(False)

        data_tup = ()
        data = ""
        # Format string for struct.unpack()
        format = '32H'

        # See if we can read anything from fd (timeout 0.05 seconds).
        ret = select.select([self.fd], [], [], 0.05)
        if (not ret[0]):
            # Poll the device to try and get some data.
            cret = c.comedi_poll(self.dev, SUBDEVICE)
            if (cret < 0):
                print("comedi poll fail: %d" % ret)
        else:
            # Read some data!
            data = os.read(self.fd, FD_BUF_SIZE)
            self.data_buf += data

        if (len(self.data_buf) > 64):
            bytes_read = len(data)
            
            #print("Read %d bytes" % bytes_read)
            # Number of rows of data in the chunk
            r = math.floor(len(self.data_buf)/(self.comedi_num_chans*WORD_SIZE))
            #print(r)
            for i in range(int(r)):
                #print(len(data[64*i:64*(i+1)]))
                #print(len(self.data_buf[64*i:64*(i+1)]))
                data_tup = data_tup + struct.unpack(format, self.data_buf[64*i:64*(i+1)])
                #print(data_tup)
                #print(data_tup)
                #data_tup = ()
            #print(len(data_tup))
            
            for n, point in enumerate(data_tup):
                self.analog_data[n%self.comedi_num_chans].append(point)
                #print(n, n%32)
                #print(point)
            for i in range(int(r)):
                self.last_x += 1.0/SCAN_FREQ
                #self.x.append(self.x[-1] + 1.0/SCAN_FREQ)
                self.x.append(self.last_x)

            for i in range(32):
                self.last_analog[i] = self.analog_data[i][-1]
                
            self.data_buf = self.data_buf[len(data_tup*2):]
            #print("LEFTOVER DATA:")
            #print(len(self.data_buf))
            #print(self.analog_data[0])

    # Old, probably don't need anymore...
    def get_batch(self):
        return(self.x, self.analog_data)

    # Get the last measurement taken for each channel. This does not
    # clear any data.
    def get_last(self):
        return(self.last_x, self.last_analog)

    # Returns data and clears queues. Thus it provides only new data
    # since last call to get_new().
    def get_new(self):
        x = list(self.x)
        self.x.clear()
        y = []
        for i in range(32):
            y.append(list(self.analog_data[i]))
            self.analog_data[i].clear()
        return(x, y)

    # Start actual hardware acquistion
    def start(self):
        # Start data acquisition
        # Start comedi command
        ret = c.comedi_command(self.dev, self.cmd)
        if (ret != 0):
            print("PCI-6033E cannot collect data! Error: %d" % ret)
            print(c.comedi_strerror(c.comedi_errno()))
            #return(False)

    # Stop hardware acquisition
    def stop(self):
        ret = c.comedi_cancel(self.dev, SUBDEVICE)
        if (ret < 0):
            print("Couldn't cancel comedi command...")
        self.data_buf = ""
        # Clear x
        self.x.clear()
        for arr in self.analog_data:
            arr.clear()
        #self.x.extend([0]*self.fifo_size)
        self.last_x = 0
        #for i in range(NUM_CHANNELS):
        #    self.analog_data[i].extend([0]*self.fifo_size)

    # Call before closing program.
    def close(self):
        c.comedi_close(self.dev)


# Helper function for showing command parameters
def print_cmd(cmd):
	print "---------------------------"
	print "command structure contains:"
	print "cmd.subdev : ", cmd.subdev
	print "cmd.flags : ", cmd.flags
	print "cmd.start :\t", cmd.start_src, "\t", cmd.start_arg
	print "cmd.scan_beg :\t", cmd.scan_begin_src, "\t", cmd.scan_begin_arg
	print "cmd.convert :\t", cmd.convert_src, "\t", cmd.convert_arg
	print "cmd.scan_end :\t", cmd.scan_end_src, "\t", cmd.scan_end_arg
	print "cmd.stop :\t", cmd.stop_src, "\t", cmd.stop_arg
	print "cmd.chanlist : ", cmd.chanlist
	print "cmd.chanlist_len : ", cmd.chanlist_len
	print "cmd.data : ", cmd.data
	print "cmd.data_len : ", cmd.data_len
	print "---------------------------"


def main():
    app = QtGui.QApplication(sys.argv)

    w = AnalogDAQWindow()
    w.show()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()