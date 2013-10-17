import comedi as c
import os
import select
import struct
import numpy as np
import math
import collections
import itertools



#import matplotlib.animation as ma
from matplotlib.figure import Figure
#from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo as FigureCanvas
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
#from matplotlib.backends.backend_gtkagg import FigureCanvasGTKAgg as FigureCanvas
#from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3 as NavigationToolbar

import matplotlib.pyplot
print matplotlib.pyplot.get_backend()

#import gtk
from gi.repository import GObject, Gtk


DEVICE = "/dev/comedi0"
SUBDEVICE = 0
# Buffer for reading the file device.
BUF_SIZE = 10000
# Scans of all 32 channels per second
SCAN_FREQ = 100
# 2 bytes per word
WORD_SIZE = 2
# Channel we want to use for 0-5 V
CHAN_RANGE = 8
NUM_CHANNELS = 32


UI_INFO = """
<ui>
  <toolbar name='ToolBar'>
    <toolitem action='Acquire' />
  </toolbar>
</ui>
"""



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


class ChessAnalogWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="CHESS Analog")
        self.set_default_size(800, 600)

        self.dev = None
        # number of plot points to plot at any one time.
        self.fifo_size = 1000
        # Buffer for plot data
        self.analog_data = []
        #self.analog_data = [32*collections.deque(self.fifo_size*[0], self.fifo_size)]
        # Init plot data container
        for i in range(NUM_CHANNELS):
            self.analog_data.append(collections.deque(self.fifo_size*[0], self.fifo_size))
        self.x = collections.deque(self.fifo_size*[0], self.fifo_size)
        # Buffer for reading from file device.
        self.data_buf = ""

        self.connect("destroy", self.on_destroy)

        # Initialize the DAQ card
        if (self.pci_6033e_init(DEVICE) < 0):
            warn_dialog("Could not initialize comedi device -- closing")
            # Quit if we can't get the daq...
            Gtk.main_quit()
        
        print("Comedi device successfully initialized \n\n")

        self.master_vbox = Gtk.Box(spacing = 2, orientation = 'vertical')
        self.master_hbox = Gtk.Box(spacing = 2)

        #self.master_vbox.pack_start(self.master_hbox, True, True, 0)
        self.add(self.master_vbox)

        self.action_acq = Gtk.ToggleAction("Acquire", "Acquire", "Get the datas", None)
        self.action_acq.connect("toggled", self.acquire_cb)

        toolbar_action_group = Gtk.ActionGroup("toolbar_actions")
        toolbar_action_group.add_action(self.action_acq)

        # UI Stuff
        uimanager = Gtk.UIManager()

        # Throws exception if something went wrong
        uimanager.add_ui_from_string(UI_INFO)
        uimanager.insert_action_group(toolbar_action_group)
        
        toolbar = uimanager.get_widget("/ToolBar")
        self.master_vbox.pack_start(toolbar, False, False, 0)


        self.liststore = Gtk.ListStore(str, float)
        for i in range(32):
            self.liststore.append([str(i), 0])

        self.treeview = Gtk.TreeView(model=self.liststore)
        
        chan_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Channel", chan_text, text=0)
        self.treeview.append_column(column_text)

        meas_text = Gtk.CellRendererText()
        mcolumn_text = Gtk.TreeViewColumn("Measurement", meas_text, text=1)
        self.treeview.append_column(mcolumn_text)

        self.master_vbox.pack_start(self.master_hbox, True, True, 0)
        #self.add(treeview)
        self.master_hbox.pack_start(self.treeview, False, False, 0)

        #self.liststore[31][1] = 18000
        #GObject.timeout_add(200, self.my_timer)
        self.timer_id = None
        self.plot_id = None

        self.f = Figure(figsize=(8,6), dpi=100)
        self.a = self.f.add_subplot(111)
        
        #self.line, = self.a.plot([], [], marker = 'x')
        #self.line, = self.a.plot([], [])
        #self.plt = self.a.plot([0, 1], [0, 3], marker = 'x')
        self.a.xaxis.set_animated(True)
        self.a.yaxis.set_animated(True)

        #self.a.set_xlim([0,5])
        self.a.set_xlim([self.fifo_size/SCAN_FREQ, 0])
        
        self.a.set_ylim([0,70000])
        
        self.a.grid(True)
        #self.a.set_xscale('log')
        #self.a.set_xlim((10.0, 30000.0))
        #self.a.set_ylim((-90.0, 3.0))
        self.a.set_xlabel("Time")
        self.a.set_ylabel("Voltage")

        self.lastx = 0
        self.my_line, = self.a.plot([], [], animated = True)
        self.my_line2, = self.a.plot([], [], animated = True)
        
        self.canvas = FigureCanvas(self.f)

        # Clean background
        self.clean_bg = self.canvas.copy_from_bbox(self.f.bbox)
        self.background = self.canvas.copy_from_bbox(self.get_bg_bbox(self.a))

        self.old_size = self.a.bbox.width, self.a.bbox.height

        self.canvas.draw()

        self.do_redraw = False

        #self.plot_timer = self.canvas.new_timer(interval = 42)

        # self.anim = ma.FuncAnimation(self.f, 
        #                              self.update_plots, 
        #                              event_source = self.plot_timer, 
        #                              init_func = self.init_blit_plot, 
        #                              repeat = False,
        #                              blit = True)

        #print(dir(self.anim))
        #self.anim._stop()
        #self.plot_timer.stop()
        self.master_hbox.pack_start(self.canvas, True, True, 0)
        #self.plot_timer.stop()

        self.connect("check-resize", self.win_resize)

    def acquire_cb(self, state):
        #print("acq callback")
        #print(state)
        if (self.action_acq.get_active()):
            # This is commented because it seems that comedi_cancel()
            # clears stale data in the fd and card?
            #data = os.read(self.fd, BUF_SIZE)
            #print("LEN DATA: %d" % len(data))

            # Start comedi command
            ret = c.comedi_command(self.dev, self.cmd)
            if (ret != 0):
                self.warn_dialog("PCI-6033E cannot collect data! Error: %d" % ret)
                print(c.comedi_strerror(c.comedi_errno()))
                return(False)



            #self.timer_id = GObject.timeout_add(100, self.my_timer)
            # Make these timeouts configurable...
            self.plotter_id = GObject.timeout_add(250, self.update_plots)
            self.plot_id = GObject.timeout_add(500, self.num_data_timer)
            self.timer_id = GObject.timeout_add(20, self.pci_6033e_get_data)
            #self.plot_timer.start()
            self.action_acq.set_label("Halt")
        else:
            self.action_acq.set_label("Acquire")
            if (self.timer_id):
                if (c.comedi_cancel(self.dev, SUBDEVICE) < 0):
                    print("failed to cancel comedi command...")
                GObject.source_remove(self.timer_id)
            if (self.plot_id):
                GObject.source_remove(self.plot_id)
            if (self.plotter_id):
                GObject.source_remove(self.plotter_id)
            #self.plot_timer.stop()
            # Empty stale data
            self.data_buf = ""
            # print(self.x)
            # print(self.analog_data[0])

    # Get the bounding box
    def get_bg_bbox(self, axe):
        # just pad x0 by three....
        return axe.bbox.padded(-3)

    def num_data_timer(self):
        # Print numerical data to treeview
        for i in range(32):
            #     datal.append(c.comedi_to_phys(j, crange, maxdata))
            self.liststore[i][1] = c.comedi_to_phys(self.analog_data[i][-1], 
                                                    self.comedi_range, 
                                                    (self.comedi_maxdata + 1))
            
        return(True)

    def pci_6033e_get_data(self):
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
            data = os.read(self.fd, BUF_SIZE)
            self.data_buf += data

        if (len(data) > 0):
            bytes_read = len(data)
            #print("Read %d bytes" % bytes_read)
            # Number of rows of data in the chunk
            r = math.floor(len(self.data_buf)/(self.comedi_num_chans*WORD_SIZE))
            for i in range(int(r)):
                #print(len(data[64*i:64*(i+1)]))
                data_tup = data_tup + struct.unpack(format, self.data_buf[64*i:64*(i+1)])
                #print(data_tup)
                #data_tup = ()
                #print(len(data))
            
            for n, point in enumerate(data_tup):
                self.analog_data[n%self.comedi_num_chans].append(point)
            for i in range(int(r)):
                self.x.append(self.x[-1] + 1.0/SCAN_FREQ)

            self.data_buf = self.data_buf[len(data_tup*2):]
            #print("LEFTOVER DATA:")
            #print(len(self.data_buf))

        return(True)

    def pci_6033e_init(self, dev_name):
        self.dev = c.comedi_open(dev_name)
        if not(self.dev):
            self.warn_dialog("Unable to open device: " + dev_name)
            return(-1)

        ret = c.comedi_lock(self.dev, SUBDEVICE)
        if (ret < 0):
            self.warn_dialog("Could not lock comedi device")
            return(-1)

        # get a file-descriptor for use later
        self.fd = c.comedi_fileno(self.dev)
        if (self.fd <= 0): 
            self.warn_dialog("Error obtaining Comedi device file descriptor")
            c.comedi_close(self.dev)
            return(-1)

        # Channel range (0-5V)
        if (c.comedi_range_is_chan_specific(self.dev, SUBDEVICE) != 0):
            self.warn_dialog("Comedi range is channel specific!")
            c.comedi_close(self.dev)
            return(-1)

        self.comedi_range = c.comedi_get_range(self.dev, SUBDEVICE, 0, CHAN_RANGE)
        self.comedi_maxdata = c.comedi_get_maxdata(self.dev, SUBDEVICE, 0)

        board_name = c.comedi_get_board_name(self.dev)
        if (board_name != "pci-6033e"):
            print("Opened wrong device!")
        
        # Prepare channels, gains, refs
        self.comedi_num_chans = NUM_CHANNELS
        chans = range(self.comedi_num_chans)
        gains = [0]*self.comedi_num_chans
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
            self.warn_dialog("Could not initiate command")
            c.comedi_close(self.dev)
            return(-1)

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
            self.warn_dialog("Comedi command test failed!")
            c.comedi_close(self.dev)
            return(-1)

        print("Command test passed")

        return(0)

    # Die gracefully...
    def on_destroy(self, widget):
        if (self.dev):
            c.comedi_close(self.dev)
            print("Comedi device closed...")
        Gtk.main_quit()

    # Oy! 
    def warn_dialog(self, message):
        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.WARNING,
                                   Gtk.ButtonsType.OK, "OHNOES!")
        dialog.format_secondary_text(message)
        response = dialog.run()

        # if response == Gtk.ResponseType.OK:
        #     print "WARN dialog closed by clicking OK button"

        dialog.destroy()

    def del_px_data(self, d_x):
        xpx_old, ypx_old = self.a.transData.transform((0, 0))
        xpx_new, ypx_new = self.a.transData.transform((d_x, 0))

        return(xpx_new - xpx_old)

    def update_plots(self):
        if (self.do_redraw):
            #print("redraw")
            self.a.clear()
            self.a.grid(True)
            self.canvas.draw()
            self.clean_bg = self.canvas.copy_from_bbox(self.f.bbox)
            self.background = self.canvas.copy_from_bbox(self.get_bg_bbox(self.a))
            self.do_redraw = False


        self.a.set_xlim([self.x[-1] - self.fifo_size/SCAN_FREQ - 1, self.x[-1] + 1])
        # Restore the blank background
        self.canvas.restore_region(self.clean_bg)

        xarr = np.array(self.x)
        analog_arr = np.array(self.analog_data[0])
        analog_arr2 = np.array(self.analog_data[18])

        #lastx_ind = np.where(np.array(self.x) > self.lastx)
        lastx_ind = np.where(xarr > self.lastx)
        #lastx_ind = itertools.islice(self.lastx

        #print(lastx_ind[0])
        lastx_ind = lastx_ind[0]

        # Offset in time
        x_offset = abs(xarr[-1] - self.lastx)

        # Find the equivalent offset in display pixels
        pixel_offset = self.del_px_data(x_offset)
        dx_pixel = np.floor(pixel_offset)


        # Compute and redraw saved background (moved over).
        x1, y1, x2, y2 = self.background.get_extents()
        self.canvas.restore_region(self.background,
                                   bbox = (x1 + dx_pixel, y1, x2, y2),
                                   xy = (x1 - dx_pixel, y1))

        
        
        # if (len(lastx_ind) > 0):
        #     lastx_ind = np.array(itertools.islice(self.x, lastx_ind[0], self.fifo_size))
        # else:
        #     lastx_ind = np.array(self.x)
        # #print(lastx_ind)

        self.my_line.set_xdata(xarr[lastx_ind])
        self.my_line.set_ydata(analog_arr[lastx_ind])
        self.a.draw_artist(self.my_line)
        #self.canvas.draw()
        self.my_line2.set_xdata(xarr[lastx_ind])
        self.my_line2.set_ydata(analog_arr2[lastx_ind])
        self.a.draw_artist(self.my_line2)

        
        self.background = self.canvas.copy_from_bbox(self.get_bg_bbox(self.a))

        # Draw the axes (and grids if applicable)
        self.a.draw_artist(self.a.xaxis)
        self.a.draw_artist(self.a.yaxis)
        
        self.canvas.blit(self.f.bbox)
        self.lastx = self.x[-1]

        #self.canvas.draw()
        return(True)

    # def init_blit_plot(self):
    #     l = self.line.set_data([], [])
    #     return(l)

    def win_resize(self, win):
        #print("RESIZE!")

        # Don't do this here, instead activate a "needs redraw" class
        # var that instructs update_plot to do a full redraw.

        self.do_redraw = True


if __name__ == '__main__':
    # args: device, # of channels
    #main(DEVICE, 32)

    
    win = ChessAnalogWindow()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()
