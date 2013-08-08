import comedi as c
import os
import select
import struct
import numpy as np
import math

from gi.repository import Gtk, GObject

DEVICE = "/dev/comedi0"
SUBDEVICE = 0
# Buffer for reading the file device.
BUF_SIZE = 10000
# Scans of all 32 channels per second
SCAN_FREQ = 1000
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


def main(dev_name, num_chans):
    dev = c.comedi_open(dev_name)
    if not(dev):
        raise Exception("Unable to open device: " + dev_name)

    # get a file-descriptor for use later
    fd = c.comedi_fileno(dev)
    if (fd <= 0): 
        raise Exception("Error obtaining Comedi device file descriptor")

    crange = c.comedi_get_range(dev, SUBDEVICE, 0, CHAN_RANGE)
    maxdata = c.comedi_get_maxdata(dev, SUBDEVICE, 0)

    board_name = c.comedi_get_board_name(dev)
    if (board_name != "pci-6033e"):
        print("Opened wrong device!")
    
    # Prepare channels, gains, refs
    chans = range(num_chans)
    gains = [0]*num_chans
    aref = [c.AREF_GROUND]*num_chans

    chan_list = c.chanlist(num_chans)

    # Configure all the channels!
    for i in range(num_chans):
        chan_list[i] = c.cr_pack(chans[i], gains[i], aref[i])

    # The comedi command
    cmd = c.comedi_cmd_struct()

    # 1.0e9 because this number is in nanoseconds for some reason
    period = int(1.0e9/float(SCAN_FREQ))

    # Init cmd
    ret = c.comedi_get_cmd_generic_timed(dev, SUBDEVICE, cmd, num_chans, period)
    if (ret):
        raise Exception("Could not initiate command")

    # Populate command 
    cmd.chanlist = chan_list
    cmd.chanlist_len = num_chans
    cmd.scan_end_arg = num_chans
    cmd.stop_src = c.TRIG_COUNT
    # TODO, short runs for now...
    cmd.stop_arg = 10

    #print("real timing: %d ns" % cmd.convert_arg)
    #print("period: %d ns" % period)
    
    print_cmd(cmd)

    # Test command out.
    ret = c.comedi_command_test(dev, cmd)
    if (ret < 0):
        raise Exception("Command test failed!")

    print("Command test passed")

    # Run the command
    ret = c.comedi_command(dev, cmd)
    if (ret != 0):
        raise Exception("command run failed")

    datastr = ()
    l = []
    data = ""
    payload = ""
    bytes_read = 0
    num_reads = 0

    datal = []    
    #format = `n`+'H'
    format = '32H'
    
    # Get the data.
    while (1):
        # ret = c.comedi_poll(dev, 0)
        # if (ret < 0):
        #     print("comedi poll fail: %d" % ret)
        ret = select.select([fd], [], [], 0.05)
        #print(ret[0])
        if (len(ret[0]) == 0):
            cret = c.comedi_poll(dev, SUBDEVICE)
            if (cret < 0):
                print("comedi poll fail: %d" % ret)
        else:
            
            data = os.read(fd, BUF_SIZE)
        #print(data)

        if (len(data) > 0):
            bytes_read += len(data)
            print("Read %d bytes" % len(data))
            #print("total read: %d" % bytes_read)
            r = math.floor(len(data)/(num_chans*WORD_SIZE))
            print(r)
            for i in range(int(r)):
                #for j in range(num_chans):
                    #print(len(data))
                print(len(data[64*i:64*(i+1)]))
                datastr = datastr + struct.unpack(format, data[64*i:64*(i+1)])
                # for j in datastr:
                #     datal.append(c.comedi_to_phys(j, crange, maxdata))
                print(datastr)
                #print(datal)
                datastr = ()
                #datal = []
            payload += data
            num_reads += 1
        if (bytes_read >= 640):
                break

            # print(type(data))
            # if (len(data) == 0):
            #     break
            # n = len(data)/2 # 2 bytes per 'H'
            # print(n)
            # format = `n`+'H'
            # #print(struct.unpack(format,data))
            # datastr = datastr + struct.unpack(format,data)
            # print(datastr)

    #print("payload: " + payload)
    print("payload len: %d" % len(payload))
    print("number of reads: %d" % num_reads)
    # print("data: ")
    # print("data len: %d" % len(datastr))
    # print(datastr)
    # print(type(datastr[0]))

    # print(maxdata)
    # for i in range(255):
    #     print(("%d  " % i) +  str(c.comedi_to_phys(i, crange, maxdata)))
    
    # blah = os.read(fd, BUF_SIZE)
    # print("blah")
    # print(len(blah))
    
    ret = c.comedi_close(dev)
    if (ret != 0):
        raise Exception("comedi_close failed...")


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


        self.liststore = Gtk.ListStore(str, int)
        for i in range(32):
            self.liststore.append([str(i), 0])

        treeview = Gtk.TreeView(model=self.liststore)
        
        chan_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Channel", chan_text, text=0)
        treeview.append_column(column_text)

        meas_text = Gtk.CellRendererText()
        mcolumn_text = Gtk.TreeViewColumn("Measurement", meas_text, text=1)
        treeview.append_column(mcolumn_text)

        self.master_vbox.pack_start(self.master_hbox, True, True, 0)
        #self.add(treeview)
        self.master_hbox.pack_start(treeview, False, False, 0)

        #self.liststore[31][1] = 18000
        #GObject.timeout_add(200, self.my_timer)
        self.timer_id = None

    def acquire_cb(self, state):
        print("acq callback")
        print(state)
        if (self.action_acq.get_active()):
            self.timer_id = GObject.timeout_add(200, self.my_timer)
            self.action_acq.set_label("Halt")
        else:
            self.action_acq.set_label("Acquire")
            if (self.timer_id):
                GObject.source_remove(self.timer_id)

    def my_timer(self):
        #print("BUMP")
        for i in range(32):
            self.liststore[i][1] += 1
            self.liststore[i][1] = self.liststore[i][1] % 65535
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

        comedi_range = c.comedi_get_range(self.dev, SUBDEVICE, 0, CHAN_RANGE)
        comedi_maxdata = c.comedi_get_maxdata(self.dev, SUBDEVICE, 0)

        board_name = c.comedi_get_board_name(self.dev)
        if (board_name != "pci-6033e"):
            print("Opened wrong device!")
        
        # Prepare channels, gains, refs
        num_chans = NUM_CHANNELS
        chans = range(num_chans)
        gains = [0]*num_chans
        aref = [c.AREF_GROUND]*num_chans

        chan_list = c.chanlist(num_chans)

        # Configure all the channels!
        for i in range(num_chans):
            chan_list[i] = c.cr_pack(chans[i], gains[i], aref[i])

        # The comedi command
        cmd = c.comedi_cmd_struct()

        # 1.0e9 because this number is in nanoseconds for some reason
        period = int(1.0e9/float(SCAN_FREQ))

        # Init cmd
        ret = c.comedi_get_cmd_generic_timed(self.dev, SUBDEVICE, cmd, num_chans, period)
        if (ret):
            self.warn_dialog("Could not initiate command")
            c.comedi_close(self.dev)
            return(-1)

        # Populate command 
        cmd.chanlist = chan_list
        cmd.chanlist_len = num_chans
        cmd.scan_end_arg = num_chans
        cmd.stop_src = c.TRIG_COUNT
        # TODO, short runs for now...
        cmd.stop_arg = 10

        #print("real timing: %d ns" % cmd.convert_arg)
        #print("period: %d ns" % period)
    
        print_cmd(cmd)

        # Test command out.
        ret = c.comedi_command_test(self.dev, cmd)
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


if __name__ == '__main__':
    # args: device, # of channels
    #main(DEVICE, 32)

    
    win = ChessAnalogWindow()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()
