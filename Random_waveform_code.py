#!/usr/bin/env python
# coding: utf-8

# In[12]:


import pyvisa as pyv
import csv
import struct
import os
import redis
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np

class WaveformGenerator:
    def __init__(self, resource_string: str, redis_host: str = 'localhost', redis_port: int = 6379):
        self.rm = pyv.ResourceManager()
        self.device = self.rm.open_resource(resource_string)
        response = self.device.query('*IDN?')
        print("Instrument ID:", response)
        self.redis_client = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)

    def send_command(self, command: str) -> None:
        print(f"Sending command: {command}")
        self.device.write(command)

    def query_command(self, command: str) -> str:
        print(f"Querying command: {command}")
        return self.device.query(command)

    def set_waveform_type(self, channel: int, waveform_type: str) -> None:
        self.send_command(f'C{channel}:BSWV WVTP,{waveform_type}')

    def set_frequency(self, channel: int, frequency: float) -> None:
        self.send_command(f'C{channel}:BSWV FRQ,{frequency}')

    def set_amplitude(self, channel: int, amplitude: float) -> None:
        self.send_command(f'C{channel}:BSWV AMP,{amplitude}')

    def set_phase(self, channel: int, phase: float) -> None:
        self.send_command(f'C{channel}:BSWV PHSE,{phase}')

    def set_offset(self, channel: int, offset: float) -> None:
        self.send_command(f'C{channel}:BSWV OFST,{offset}')

    def start_waveform(self, channel: int) -> None:
        self.send_command(f'C{channel}:OUTP ON')

    def stop_waveform(self, channel: int) -> None:
        self.send_command(f'C{channel}:OUTP OFF')

    def set_arbitrary_waveform_by_name(self, channel: int, name: str) -> None:
        self.send_command(f'C{channel}:ARWV NAME,{name}')

    def query_arbitrary_waveform(self, channel: int) -> str:
        return self.query_command(f'C{channel}:ARWV?')

    def convert_csv_to_binary(self, csv_filename: str, bin_filename: str) -> None:
        if not os.path.isfile(csv_filename):
            raise FileNotFoundError(f"No such file: '{csv_filename}'")
        with open(csv_filename, 'r') as csvfile, open(bin_filename, 'wb') as binfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip the header row
            for row in reader:
                float_row = list(map(float, row))
                bin_row = struct.pack('f' * len(float_row), *float_row)
                binfile.write(bin_row)
        print(f"Converted {csv_filename} to {bin_filename}")

    def save_binary_waveform_to_device(self, bin_filename: str) -> None:
        waveform_name = os.path.splitext(os.path.basename(bin_filename))[0]  # Use filename without extension as the waveform name
        with open(bin_filename, 'rb') as binfile:
            data = binfile.read()
            self.device.write_binary_values(f'C1:WVDT WVNM,{waveform_name},WAVEDATA,', data, datatype='B')
        print(f"Binary waveform {bin_filename} saved to device as {waveform_name}.")

    def upload_and_generate_waveform(self, channel: int, csv_filename: str, frequency, amplitude, phase, offset):
        bin_filename = os.path.splitext(csv_filename)[0] + '.bin'
        self.convert_csv_to_binary(csv_filename, bin_filename)
        self.save_binary_waveform_to_device(bin_filename)
        self.set_arbitrary_waveform_by_name(channel, os.path.splitext(os.path.basename(csv_filename))[0])
        self.set_frequency(channel, frequency)
        self.set_amplitude(channel, amplitude)
        self.set_phase(channel, phase)
        self.set_offset(channel, offset)
        self.start_waveform(channel)
        print(f"Waveform from {csv_filename} is now being generated on channel {channel}")

    def get_command_from_redis(self, key: str):
        return self.redis_client.get(key)

    def set_command_to_redis(self, key: str, value: str):
        self.redis_client.set(key, value)

class WaveformGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Waveform Generator Configuration")

        self.connection_type = tk.StringVar()
        self.address = tk.StringVar()
        self.mode = tk.StringVar()
        self.channel = tk.IntVar(value=1)
        self.waveform_type = tk.StringVar()
        self.frequency = tk.DoubleVar()
        self.amplitude = tk.DoubleVar()
        self.phase = tk.DoubleVar()
        self.offset = tk.DoubleVar()
        self.redis_key = tk.StringVar()
        self.file_path = tk.StringVar()

        self.figure = Figure(figsize=(5, 2), dpi=100)
        self.create_widgets()
        self.plot_waveform()

    def create_widgets(self):
        # Connection type and address
        ttk.Label(self.root, text="Select Connection Type:").grid(column=0, row=0, padx=10, pady=10)
        connection_menu = ttk.Combobox(self.root, textvariable=self.connection_type)
        connection_menu['values'] = ('LAN', 'GPIB')
        connection_menu.grid(column=1, row=0, padx=10, pady=10)

        ttk.Label(self.root, text="Enter Address:").grid(column=0, row=1, padx=10, pady=10)
        ttk.Entry(self.root, textvariable=self.address).grid(column=1, row=1, padx=10, pady=10)

        # Mode selection
        ttk.Label(self.root, text="Select Mode:").grid(column=0, row=2, padx=10, pady=10)
        mode_menu = ttk.Combobox(self.root, textvariable=self.mode)
        mode_menu['values'] = ('Manual', 'Redis', 'Custom')
        mode_menu.grid(column=1, row=2, padx=10, pady=10)
        mode_menu.bind('<<ComboboxSelected>>', self.mode_selected)

        ttk.Label(self.root, text="Channel:").grid(column=0, row=3, padx=10, pady=10)
        ttk.Spinbox(self.root, from_=1, to=2, textvariable=self.channel).grid(column=1, row=3, padx=10, pady=10)

        self.manual_frame = ttk.Frame(self.root)
        self.redis_frame = ttk.Frame(self.root)
        self.custom_frame = ttk.Frame(self.root)

        self.create_manual_widgets()
        self.create_redis_widgets()
        self.create_custom_widgets()

        ttk.Button(self.root, text="Connect", command=self.connect_device).grid(column=0, row=4, columnspan=2, pady=10)
        self.canvas = FigureCanvasTkAgg(self.figure, self.root)
        self.canvas.get_tk_widget().grid(column=0, row=5, columnspan=2, pady=10)

    def create_manual_widgets(self):
        ttk.Label(self.manual_frame, text="Waveform Type:").grid(column=0, row=0, padx=10, pady=10)
        self.waveform_type_menu = ttk.Combobox(self.manual_frame, textvariable=self.waveform_type)
        self.waveform_type_menu['values'] = ('Sine', 'Square', 'Ramp', 'Pulse', 'Noise', 'DC')
        self.waveform_type_menu.grid(column=1, row=0, padx=10, pady=10)
        self.waveform_type_menu.bind('<<ComboboxSelected>>', self.update_waveform_type)

        self.waveform_type_entry = ttk.Entry(self.manual_frame, textvariable=self.waveform_type)
        self.waveform_type_entry.grid(column=2, row=0, padx=10, pady=10)
        self.waveform_type_entry.bind('<Return>', self.update_waveform_type)

        ttk.Label(self.manual_frame, text="Frequency (Hz):").grid(column=0, row=1, padx=10, pady=10)
        self.frequency_slider = ttk.Scale(self.manual_frame, from_=0, to=50000000, orient=tk.HORIZONTAL, variable=self.frequency, command=self.update_frequency_entry)
        self.frequency_slider.grid(column=1, row=1, padx=10, pady=10)
        self.frequency_entry = ttk.Entry(self.manual_frame, textvariable=self.frequency)
        self.frequency_entry.grid(column=2, row=1, padx=10, pady=10)
        self.frequency_entry.bind('<Return>', self.update_frequency_entry)

        ttk.Label(self.manual_frame, text="Amplitude (V):").grid(column=0, row=2, padx=10, pady=10)
        self.amplitude_slider = ttk.Scale(self.manual_frame, from_=0, to=10, orient=tk.HORIZONTAL, variable=self.amplitude, command=self.update_amplitude_entry)
        self.amplitude_slider.grid(column=1, row=2, padx=10, pady=10)
        self.amplitude_entry = ttk.Entry(self.manual_frame, textvariable=self.amplitude)
        self.amplitude_entry.grid(column=2, row=2, padx=10, pady=10)
        self.amplitude_entry.bind('<Return>', self.update_amplitude_entry)

        ttk.Label(self.manual_frame, text="Phase (degrees):").grid(column=0, row=3, padx=10, pady=10)
        self.phase_slider = ttk.Scale(self.manual_frame, from_=0, to=360, orient=tk.HORIZONTAL, variable=self.phase, command=self.update_phase_entry)
        self.phase_slider.grid(column=1, row=3, padx=10, pady=10)
        self.phase_entry = ttk.Entry(self.manual_frame, textvariable=self.phase)
        self.phase_entry.grid(column=2, row=3, padx=10, pady=10)
        self.phase_entry.bind('<Return>', self.update_phase_entry)

        ttk.Label(self.manual_frame, text="Offset (V):").grid(column=0, row=4, padx=10, pady=10)
        self.offset_slider = ttk.Scale(self.manual_frame, from_=-5, to=5, orient=tk.HORIZONTAL, variable=self.offset, command=self.update_offset_entry)
        self.offset_slider.grid(column=1, row=4, padx=10, pady=10)
        self.offset_entry = ttk.Entry(self.manual_frame, textvariable=self.offset)
        self.offset_entry.grid(column=2, row=4, padx=10, pady=10)
        self.offset_entry.bind('<Return>', self.update_offset_entry)

        ttk.Button(self.manual_frame, text="Set Waveform", command=self.set_waveform_manual).grid(column=0, row=5, columnspan=3, pady=10)

    def create_redis_widgets(self):
        ttk.Label(self.redis_frame, text="Redis Key:").grid(column=0, row=0, padx=10, pady=10)
        ttk.Entry(self.redis_frame, textvariable=self.redis_key).grid(column=1, row=0, padx=10, pady=10)

        ttk.Button(self.redis_frame, text="Execute Command", command=self.execute_redis_command).grid(column=0, row=1, columnspan=2, pady=10)

    def create_custom_widgets(self):
        ttk.Label(self.custom_frame, text="Select File:").grid(column=0, row=0, padx=10, pady=10)
        ttk.Entry(self.custom_frame, textvariable=self.file_path).grid(column=1, row=0, padx=10, pady=10)
        ttk.Button(self.custom_frame, text="Browse", command=self.browse_file).grid(column=2, row=0, padx=10, pady=10)

        ttk.Label(self.custom_frame, text="Frequency (Hz):").grid(column=0, row=1, padx=10, pady=10)
        self.custom_frequency_entry = ttk.Entry(self.custom_frame, textvariable=self.frequency)
        self.custom_frequency_entry.grid(column=1, row=1, padx=10, pady=10)

        ttk.Label(self.custom_frame, text="Amplitude (V):").grid(column=0, row=2, padx=10, pady=10)
        self.custom_amplitude_entry = ttk.Entry(self.custom_frame, textvariable=self.amplitude)
        self.custom_amplitude_entry.grid(column=1, row=2, padx=10, pady=10)

        ttk.Label(self.custom_frame, text="Phase (degrees):").grid(column=0, row=3, padx=10, pady=10)
        self.custom_phase_entry = ttk.Entry(self.custom_frame, textvariable=self.phase)
        self.custom_phase_entry.grid(column=1, row=3, padx=10, pady=10)

        ttk.Label(self.custom_frame, text="Offset (V):").grid(column=0, row=4, padx=10, pady=10)
        self.custom_offset_entry = ttk.Entry(self.custom_frame, textvariable=self.offset)
        self.custom_offset_entry.grid(column=1, row=4, padx=10, pady=10)

        ttk.Button(self.custom_frame, text="Upload and Generate", command=self.upload_and_generate).grid(column=0, row=5, columnspan=3, pady=10)

    def mode_selected(self, event):
        self.manual_frame.grid_forget()
        self.redis_frame.grid_forget()
        self.custom_frame.grid_forget()

        if self.mode.get() == 'Manual':
            self.manual_frame.grid(column=0, row=6, columnspan=3, pady=10)
        elif self.mode.get() == 'Redis':
            self.redis_frame.grid(column=0, row=6, columnspan=2, pady=10)
        elif self.mode.get() == 'Custom':
            self.custom_frame.grid(column=0, row=6, columnspan=3, pady=10)

    def connect_device(self):
        connection_type = self.connection_type.get()
        address = self.address.get()

        if connection_type == 'LAN':
            resource_string = f"TCPIP::{address}::INSTR"
        elif connection_type == 'GPIB':
            resource_string = f"GPIB::{address}::INSTR"
        else:
            print("Invalid connection type.")
            return

        self.generator = WaveformGenerator(resource_string)
        print(f"Connected to device at {resource_string}")

    def set_waveform_manual(self):
        self.generator.set_waveform_type(self.channel.get(), self.waveform_type.get())
        self.generator.set_frequency(self.channel.get(), self.frequency.get())
        self.generator.set_amplitude(self.channel.get(), self.amplitude.get())
        self.generator.set_phase(self.channel.get(), self.phase.get())
        self.generator.set_offset(self.channel.get(), self.offset.get())
        self.generator.start_waveform(self.channel.get())
        self.plot_waveform()

    def execute_redis_command(self):
        command = self.generator.get_command_from_redis(self.redis_key.get())
        parts = command.split()
        if parts[0] == 'upload':
            csv_filename = parts[2]
            if not os.path.isfile(csv_filename):
                print(f"No such file: '{csv_filename}'")
                return
            self.generator.upload_and_generate_waveform(self.channel.get(), csv_filename)
        elif parts[0] == 'set':
            waveform_type = parts[2]
            self.generator.set_waveform_type(self.channel.get(), waveform_type)
            self.generator.set_frequency(self.channel.get(), float(parts[3]))
            self.generator.set_amplitude(self.channel.get(), float(parts[4]))
            self.generator.start_waveform(self.channel.get())
        elif parts[0] == 'stop':
            self.generator.stop_waveform(self.channel.get())
        else:
            print("Unknown command.")

    def browse_file(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            self.file_path.set(file_path)

    def upload_and_generate(self):
        self.generator.upload_and_generate_waveform(self.channel.get(), self.file_path.get(), self.frequency.get(), self.amplitude.get(), self.phase.get(), self.offset.get())

    def plot_waveform(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        t = np.linspace(0, 1, 500)
        y = np.zeros_like(t)
        
        if self.waveform_type.get().lower() == 'sine':
            y = np.sin(2 * np.pi * self.frequency.get() * t)
        elif self.waveform_type.get().lower() == 'square':
            y = np.sign(np.sin(2 * np.pi * self.frequency.get() * t))
        elif self.waveform_type.get().lower() == 'ramp':
            y = 2 * (t - np.floor(t + 0.5))
        elif self.waveform_type.get().lower() == 'pulse':
            y = np.where(np.sin(2 * np.pi * self.frequency.get() * t) > 0, 1, 0)
        elif self.waveform_type.get().lower() == 'noise':
            y = np.random.normal(0, 1, len(t))
        elif self.waveform_type.get().lower() == 'dc':
            y = np.ones_like(t)

        ax.plot(t, y)
        ax.set_title(f"Waveform: {self.waveform_type.get()}")
        ax.set_xlabel("Time")
        ax.set_ylabel("Amplitude")
        self.canvas.draw()

    def update_waveform_type(self, event=None):
        self.plot_waveform()

    def update_frequency_entry(self, val):
        self.frequency_entry.delete(0, tk.END)
        self.frequency_entry.insert(0, f"{float(val):.2f}")
        self.plot_waveform()

    def update_amplitude_entry(self, val):
        self.amplitude_entry.delete(0, tk.END)
        self.amplitude_entry.insert(0, f"{float(val):.2f}")
        self.plot_waveform()

    def update_phase_entry(self, val):
        self.phase_entry.delete(0, tk.END)
        self.phase_entry.insert(0, f"{float(val):.2f}")
        self.plot_waveform()

    def update_offset_entry(self, val):
        self.offset_entry.delete(0, tk.END)
        self.offset_entry.insert(0, f"{float(val):.2f}")
        self.plot_waveform()

if __name__ == "__main__":
    root = tk.Tk()
    app = WaveformGUI(root)
    root.mainloop()


# %%
