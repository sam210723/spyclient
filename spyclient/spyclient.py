"""
spyclient.py
https://github.com/sam210723/spyclient

Airspy SpyServer client implementation for Python 3
"""

import ipaddress
from select import select
import socket
import struct
import threading
from .enums import *
from .tuples import *

## Constants
PACKAGE_VER = "1.0"             # Python package version
PROTOCOL_VER = 0x20006A4        # Protocol implementation version
DEFAULT_HOST = "127.0.0.1"      # Default socket host
DEFAULT_PORT = 5555             # Default socket port
TIMEOUT = 2                     # Socket read timeout (sec)


class SpyClient:
    """
    Airspy SpyServer client implementation for Python 3.
    :param host: SpyServer host IP address (127.0.0.1)
    :param port: SpyServer TCP port (5555)
    """

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        # Properties
        self.host = host                # SpyServer IP address
        self.port = port                # SpyServer TCP port
        self.name = f"SpyClient for Python v{PACKAGE_VER}"
        self.server_ver = 0             # SpyServer version
        self.device = None              # Server device info

        # Flags
        self.connected = False          # Client connected to server
        self.rx_stop = False            # Stop socket receive thread


    #region Protocol Functions
    def parse_msg(self, header_bytes):
        """
        Parse incoming message from server
        """

        # Check header length
        if header_bytes == None or len(header_bytes) < 20:
            return False

        # Parse header
        header_tuple = struct.unpack('IIIII', header_bytes)
        header = MessageHeader(*header_tuple)
        msg_type = MessageType(header.message_type).name

        print(msg_type)
        print(header)
        print()

        # Parse server protocol version
        self.server_ver = self.parse_protocol_ver(header.protocol)
        #TODO: Check protocol version

        # Get body of message
        body = self.recv(header.size)

        # Cast message into named tuple
        if msg_type == "DEVICE_INFO":
            # Unpack all fields except device type
            unpacked = struct.unpack('4xIIIIIIIIIII', body)
            
            # Get device type as DeviceType object
            dev_type = int.from_bytes(body[0:4], byteorder="little")
            dev_type = ( DeviceType(dev_type), )

            # Concat device type and all other fields into one tuple
            dev_tuple = dev_type + unpacked

            # Cast tuple into DeviceInfo object
            self.device = DeviceInfo(*dev_tuple)

    def parse_protocol_ver(self, data):
        """
        Parse server protocol version into ProtocolVersion named tuple
        """

        major = data >> 24
        minor = data >> 16 & 0xFF
        patch = data & 0xFFFF

        return ProtocolVersion(major, minor, patch)

    def say_hello(self):
        """
        Say hello to server
        """

        # Protocol version as unsigned little-endian integer
        ver = struct.pack('<I', PROTOCOL_VER)

        # Get bytes from client name
        client = self.name.encode('UTF-8')

        # Send version and client name to server
        body = ver + client        
        self.send_command(CommandType.HELLO.value, body)
    
    def send_command(self, cmd, body):
        """
        Sends command packet to server
        :param cmd: Command type
        :param body: Command body bytes
        """

        # Assemble command header
        length = struct.pack('<I', len(body))
        header = cmd + length

        # Send command to server
        command = header + body
        self.send(command)
    #endregion


    #region Socket Functions
    def recv_loop(self):
        """
        Socket receive thread
        """

        while not self.rx_stop:
            # Block thread until socket is ready for reading
            rx, tx, err = select([ self.sck ], [], [], TIMEOUT)

            # Socket has data available
            if rx:
                # Get message header
                header = self.recv()

                # Ignore bool len exception
                if type(header) == bool:
                    continue

                # Message header is empty
                if header == b'':
                    self.disconnect()
                    raise PermissionError("SpyServer could not find/acquire a device")

                self.parse_msg(header)
    
    def connect(self):
        """
        Connect to SpyServer
        """

        # Validate IP address
        try:
            ipaddress.ip_address(self.host)
        except ValueError:
            raise

        # Validate port
        if not (1023 < self.port < 65536):
            raise ValueError(f"Host port \"{self.port}\" is invalid")

        # Create and configure socket
        self.sck = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sck.settimeout(TIMEOUT)

        try:
            self.sck.connect((self.host, self.port))
        except socket.error:
            raise

        #TODO: Set flag after handling client sync and device info
        self.connected = True

        # Setup and start socket receive thread
        self.rx_thread = threading.Thread()
        self.rx_thread.name = "SpyClient Socket Receiver"
        self.rx_thread.run = self.recv_loop
        self.rx_thread.start()

        self.say_hello()

        return True

    def disconnect(self):
        """
        Disconnect from SpyServer
        """

        self.rx_stop = True
        self.sck.close()
        self.connected = False

    def send(self, data):
        """
        Send data to server
        """

        if not self.connected: return False
        self.sck.send(data)

    def recv(self, length=20):
        """
        Receive data from server
        """

        if not self.connected: return False
        
        try:
            return self.sck.recv(length)
        except:
            return None
    #endregion


    #region Print Functions
    def print_device_info(self):
        """
        Prints device information from server
        """

        # Loop through fields in DeviceInfo tuple
        for j in self.device._fields:
            key = j.replace("_", " ").title()
            key = key.replace("Iq", "IQ")
            key = key.replace("Adc", "ADC") + ":"

            val = getattr(self.device, j)

            # Value formatting
            if j == "device_type":        val = val.name
            elif j == "max_sample_rate":  val = str(val/1000000) + " Msps"
            elif j == "max_bandwidth":    val = str(val/1000000) + " Msps"
            elif j == "min_frequency":    val = str(val/1000000) + " MHz"
            elif j == "max_frequency":    val = str(val/1000000) + " MHz"
            elif j == "adc_resolution":   val = f"{val} bits"
            elif j == "forced_iq_format": val = bool(val)

            print(f"{key.ljust(20)}{val}")
    #endregion
