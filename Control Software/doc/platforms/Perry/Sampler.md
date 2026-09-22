# Liquid Handler Sampler usage


    Handles communication with a CNC-based sampler.
    The device is documented in detail at https://github.com/Noel-Research-Group/liquid_handler_cnc .

    Usage:
        First, connect to the device with
        `self.open('COM4')`

        Then, change parameters of the device with
        `self['parameter_name'] = xyz`

        or read parameters with
        `xyz = self['parameter_name']`

        For a detailed list of available parameters, call
        `self.parameters()`

        For a human-readable list of parameters, call
        `print(self.usage())`

        Finally, close the device with
        `self.close()`

    Notes on Grbl settings:
        The user must take care that grbl is properly set up for the machine in use.
        In addition, homing cycle ($22) must be enabled. Therefore, the machine needs physical endstops.
        It is advised to also enable softlimits ($20) and hard limits ($21) and set accurate values for the
        maximum travel setting of each axis.

    This code has been written and tested with grbl v0.9j.
    Reference: https://honingmill.fandom.com/wiki/Configuring_Grbl_v0.9
    
## Parameters:

| Name | Access | Type | Description | Values |
|------|--------|------|-------------|--------|
| **status** | READ ONLY | GrblStatus | Current machine status| | 
| **position** | READ ONLY | GrblPosition | Current machine position| | 
| **home** | WRITE ONLY | ArduinoValueRun | Run homing cycle|    value = RUN, | 
| **unlock** | WRITE ONLY | ArduinoValueRun | Unlock grbl without zeroing|    value = RUN, | 
| **offset** | WRITE ONLY | GrblPosition | Set the working coordinates to the given value| | 
| **feed** | READ/WRITE | float | Set feed-rate| 0.0 <= value <= 2000.0  mm/min, | 
| **move** | WRITE ONLY | GrblPosition | Move to an absolute work position at the feed rate| | 
| **fast_move** | WRITE ONLY | GrblPosition | Move to an absolute work position as fast as possible| | 
| **aux_needle** | WRITE ONLY | GrblAuxNeedle | Insert or retract the auxiliary needle| - OFF -> 9 , - ON -> 8 , | 
| **units_mm** | WRITE ONLY | ArduinoValueRun | Set units to mm|    value = RUN, | 
| **absolute** | WRITE ONLY | ArduinoValueRun | All coordinates are absolute values from the origin|    value = RUN, | 
| **pause** | WRITE ONLY | float | Pause execution for this many seconds| 0.01 <= value <= 1000.0 , | 
| **hold** | WRITE ONLY | ArduinoValueRun | Stops machine motion instantly. Queued motions can be resumed|    value = RUN, | 
| **resume** | WRITE ONLY | ArduinoValueRun | Resume machine operations after 'hold' state|    value = RUN, | 
| **reset** | WRITE ONLY | ArduinoValueRun | Soft reset, machine position is preserved|    value = RUN, | 
| **step_pulse** | READ/WRITE | float | | | 
| **step_idle_delay** | READ/WRITE | float | | | 
| **step_port_invert_mask** | READ/WRITE | int | | | 
| **dir_port_invert_mask** | READ/WRITE | int | | | 
| **step_enable_invert** | READ/WRITE | ArduinoValueOnOff | | - OFF -> 0 , - ON -> 1 , | 
| **limit_pins_invert** | READ/WRITE | ArduinoValueOnOff | | - OFF -> 0 , - ON -> 1 , | 
| **probe_pin_invert** | READ/WRITE | ArduinoValueOnOff | | - OFF -> 0 , - ON -> 1 , | 
| **status_report_mask** | READ/WRITE | int | | | 
| **junction_deviation** | READ/WRITE | float | | | 
| **arc_tolerance** | READ/WRITE | float | | | 
| **report_inches** | READ/WRITE | ArduinoValueOnOff | | - OFF -> 0 , - ON -> 1 , | 
| **soft_limits** | READ/WRITE | ArduinoValueOnOff | | - OFF -> 0 , - ON -> 1 , | 
| **hard_limits** | READ/WRITE | ArduinoValueOnOff | | - OFF -> 0 , - ON -> 1 , | 
| **homing_cycle** | READ/WRITE | ArduinoValueOnOff | | - OFF -> 0 , - ON -> 1 , | 
| **homing_dir_invert_mask** | READ/WRITE | int | | | 
| **homing_feed** | READ/WRITE | float | | | 
| **homing_seek** | READ/WRITE | float | | | 
| **homing_debounce** | READ/WRITE | float | | | 
| **homing_pull-off** | READ/WRITE | float | | | 
| **x_move** | READ/WRITE | float | | | 
| **y_move** | READ/WRITE | float | | | 
| **z_move** | READ/WRITE | float | | | 
| **x_max_rate** | READ/WRITE | float | | | 
| **y_max_rate** | READ/WRITE | float | | | 
| **z_max_rate** | READ/WRITE | float | | | 
| **x_accel** | READ/WRITE | float | | | 
| **y_accel** | READ/WRITE | float | | | 
| **z_accel** | READ/WRITE | float | | | 
| **x_max_travel** | READ/WRITE | float | | | 
| **y_max_travel** | READ/WRITE | float | | | 
| **z_max_travel** | READ/WRITE | float | | | 

## Setup options:
| Name | Required | Type | Description |
|------|----------|------|-------------|
| **ignore_unexpected_data** | False | bool | Receiving unexpected data via serial communication is treated as a fatalerror by default, this option allows to only issue a warning when this happens. |
| **status_ignore_timeout** | False | bool | By default, timing out on parameter status raises an exception. If this option is set to True, only a warning is issued. |
| **status_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from status raises an exception. If this option is set to True, only a warning is issued. |
| **position_ignore_timeout** | False | bool | By default, timing out on parameter position raises an exception. If this option is set to True, only a warning is issued. |
| **position_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from position raises an exception. If this option is set to True, only a warning is issued. |
| **home_ignore_timeout** | False | bool | By default, timing out on parameter home raises an exception. If this option is set to True, only a warning is issued. |
| **home_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from home raises an exception. If this option is set to True, only a warning is issued. |
| **unlock_ignore_timeout** | False | bool | By default, timing out on parameter unlock raises an exception. If this option is set to True, only a warning is issued. |
| **unlock_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from unlock raises an exception. If this option is set to True, only a warning is issued. |
| **offset_ignore_timeout** | False | bool | By default, timing out on parameter offset raises an exception. If this option is set to True, only a warning is issued. |
| **offset_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from offset raises an exception. If this option is set to True, only a warning is issued. |
| **feed_ignore_timeout** | False | bool | By default, timing out on parameter feed raises an exception. If this option is set to True, only a warning is issued. |
| **feed_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from feed raises an exception. If this option is set to True, only a warning is issued. |
| **move_ignore_timeout** | False | bool | By default, timing out on parameter move raises an exception. If this option is set to True, only a warning is issued. |
| **move_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from move raises an exception. If this option is set to True, only a warning is issued. |
| **fast_move_ignore_timeout** | False | bool | By default, timing out on parameter fast_move raises an exception. If this option is set to True, only a warning is issued. |
| **fast_move_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from fast_move raises an exception. If this option is set to True, only a warning is issued. |
| **aux_needle_ignore_timeout** | False | bool | By default, timing out on parameter aux_needle raises an exception. If this option is set to True, only a warning is issued. |
| **aux_needle_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from aux_needle raises an exception. If this option is set to True, only a warning is issued. |
| **units_mm_ignore_timeout** | False | bool | By default, timing out on parameter units_mm raises an exception. If this option is set to True, only a warning is issued. |
| **units_mm_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from units_mm raises an exception. If this option is set to True, only a warning is issued. |
| **absolute_ignore_timeout** | False | bool | By default, timing out on parameter absolute raises an exception. If this option is set to True, only a warning is issued. |
| **absolute_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from absolute raises an exception. If this option is set to True, only a warning is issued. |
| **pause_ignore_timeout** | False | bool | By default, timing out on parameter pause raises an exception. If this option is set to True, only a warning is issued. |
| **pause_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from pause raises an exception. If this option is set to True, only a warning is issued. |
| **resume_ignore_timeout** | False | bool | By default, timing out on parameter resume raises an exception. If this option is set to True, only a warning is issued. |
| **resume_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from resume raises an exception. If this option is set to True, only a warning is issued. |
| **step_pulse_ignore_timeout** | False | bool | By default, timing out on parameter step_pulse raises an exception. If this option is set to True, only a warning is issued. |
| **step_pulse_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from step_pulse raises an exception. If this option is set to True, only a warning is issued. |
| **step_idle_delay_ignore_timeout** | False | bool | By default, timing out on parameter step_idle_delay raises an exception. If this option is set to True, only a warning is issued. |
| **step_idle_delay_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from step_idle_delay raises an exception. If this option is set to True, only a warning is issued. |
| **step_port_invert_mask_ignore_timeout** | False | bool | By default, timing out on parameter step_port_invert_mask raises an exception. If this option is set to True, only a warning is issued. |
| **step_port_invert_mask_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from step_port_invert_mask raises an exception. If this option is set to True, only a warning is issued. |
| **dir_port_invert_mask_ignore_timeout** | False | bool | By default, timing out on parameter dir_port_invert_mask raises an exception. If this option is set to True, only a warning is issued. |
| **dir_port_invert_mask_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from dir_port_invert_mask raises an exception. If this option is set to True, only a warning is issued. |
| **step_enable_invert_ignore_timeout** | False | bool | By default, timing out on parameter step_enable_invert raises an exception. If this option is set to True, only a warning is issued. |
| **step_enable_invert_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from step_enable_invert raises an exception. If this option is set to True, only a warning is issued. |
| **limit_pins_invert_ignore_timeout** | False | bool | By default, timing out on parameter limit_pins_invert raises an exception. If this option is set to True, only a warning is issued. |
| **limit_pins_invert_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from limit_pins_invert raises an exception. If this option is set to True, only a warning is issued. |
| **probe_pin_invert_ignore_timeout** | False | bool | By default, timing out on parameter probe_pin_invert raises an exception. If this option is set to True, only a warning is issued. |
| **probe_pin_invert_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from probe_pin_invert raises an exception. If this option is set to True, only a warning is issued. |
| **status_report_mask_ignore_timeout** | False | bool | By default, timing out on parameter status_report_mask raises an exception. If this option is set to True, only a warning is issued. |
| **status_report_mask_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from status_report_mask raises an exception. If this option is set to True, only a warning is issued. |
| **junction_deviation_ignore_timeout** | False | bool | By default, timing out on parameter junction_deviation raises an exception. If this option is set to True, only a warning is issued. |
| **junction_deviation_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from junction_deviation raises an exception. If this option is set to True, only a warning is issued. |
| **arc_tolerance_ignore_timeout** | False | bool | By default, timing out on parameter arc_tolerance raises an exception. If this option is set to True, only a warning is issued. |
| **arc_tolerance_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from arc_tolerance raises an exception. If this option is set to True, only a warning is issued. |
| **report_inches_ignore_timeout** | False | bool | By default, timing out on parameter report_inches raises an exception. If this option is set to True, only a warning is issued. |
| **report_inches_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from report_inches raises an exception. If this option is set to True, only a warning is issued. |
| **soft_limits_ignore_timeout** | False | bool | By default, timing out on parameter soft_limits raises an exception. If this option is set to True, only a warning is issued. |
| **soft_limits_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from soft_limits raises an exception. If this option is set to True, only a warning is issued. |
| **hard_limits_ignore_timeout** | False | bool | By default, timing out on parameter hard_limits raises an exception. If this option is set to True, only a warning is issued. |
| **hard_limits_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from hard_limits raises an exception. If this option is set to True, only a warning is issued. |
| **homing_cycle_ignore_timeout** | False | bool | By default, timing out on parameter homing_cycle raises an exception. If this option is set to True, only a warning is issued. |
| **homing_cycle_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from homing_cycle raises an exception. If this option is set to True, only a warning is issued. |
| **homing_dir_invert_mask_ignore_timeout** | False | bool | By default, timing out on parameter homing_dir_invert_mask raises an exception. If this option is set to True, only a warning is issued. |
| **homing_dir_invert_mask_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from homing_dir_invert_mask raises an exception. If this option is set to True, only a warning is issued. |
| **homing_feed_ignore_timeout** | False | bool | By default, timing out on parameter homing_feed raises an exception. If this option is set to True, only a warning is issued. |
| **homing_feed_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from homing_feed raises an exception. If this option is set to True, only a warning is issued. |
| **homing_seek_ignore_timeout** | False | bool | By default, timing out on parameter homing_seek raises an exception. If this option is set to True, only a warning is issued. |
| **homing_seek_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from homing_seek raises an exception. If this option is set to True, only a warning is issued. |
| **homing_debounce_ignore_timeout** | False | bool | By default, timing out on parameter homing_debounce raises an exception. If this option is set to True, only a warning is issued. |
| **homing_debounce_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from homing_debounce raises an exception. If this option is set to True, only a warning is issued. |
| **homing_pull-off_ignore_timeout** | False | bool | By default, timing out on parameter homing_pull-off raises an exception. If this option is set to True, only a warning is issued. |
| **homing_pull-off_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from homing_pull-off raises an exception. If this option is set to True, only a warning is issued. |
| **x_move_ignore_timeout** | False | bool | By default, timing out on parameter x_move raises an exception. If this option is set to True, only a warning is issued. |
| **x_move_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from x_move raises an exception. If this option is set to True, only a warning is issued. |
| **y_move_ignore_timeout** | False | bool | By default, timing out on parameter y_move raises an exception. If this option is set to True, only a warning is issued. |
| **y_move_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from y_move raises an exception. If this option is set to True, only a warning is issued. |
| **z_move_ignore_timeout** | False | bool | By default, timing out on parameter z_move raises an exception. If this option is set to True, only a warning is issued. |
| **z_move_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from z_move raises an exception. If this option is set to True, only a warning is issued. |
| **x_max_rate_ignore_timeout** | False | bool | By default, timing out on parameter x_max_rate raises an exception. If this option is set to True, only a warning is issued. |
| **x_max_rate_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from x_max_rate raises an exception. If this option is set to True, only a warning is issued. |
| **y_max_rate_ignore_timeout** | False | bool | By default, timing out on parameter y_max_rate raises an exception. If this option is set to True, only a warning is issued. |
| **y_max_rate_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from y_max_rate raises an exception. If this option is set to True, only a warning is issued. |
| **z_max_rate_ignore_timeout** | False | bool | By default, timing out on parameter z_max_rate raises an exception. If this option is set to True, only a warning is issued. |
| **z_max_rate_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from z_max_rate raises an exception. If this option is set to True, only a warning is issued. |
| **x_accel_ignore_timeout** | False | bool | By default, timing out on parameter x_accel raises an exception. If this option is set to True, only a warning is issued. |
| **x_accel_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from x_accel raises an exception. If this option is set to True, only a warning is issued. |
| **y_accel_ignore_timeout** | False | bool | By default, timing out on parameter y_accel raises an exception. If this option is set to True, only a warning is issued. |
| **y_accel_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from y_accel raises an exception. If this option is set to True, only a warning is issued. |
| **z_accel_ignore_timeout** | False | bool | By default, timing out on parameter z_accel raises an exception. If this option is set to True, only a warning is issued. |
| **z_accel_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from z_accel raises an exception. If this option is set to True, only a warning is issued. |
| **x_max_travel_ignore_timeout** | False | bool | By default, timing out on parameter x_max_travel raises an exception. If this option is set to True, only a warning is issued. |
| **x_max_travel_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from x_max_travel raises an exception. If this option is set to True, only a warning is issued. |
| **y_max_travel_ignore_timeout** | False | bool | By default, timing out on parameter y_max_travel raises an exception. If this option is set to True, only a warning is issued. |
| **y_max_travel_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from y_max_travel raises an exception. If this option is set to True, only a warning is issued. |
| **z_max_travel_ignore_timeout** | False | bool | By default, timing out on parameter z_max_travel raises an exception. If this option is set to True, only a warning is issued. |
| **z_max_travel_ignore_badack** | False | bool | By default, receiving a bad acknowledge value from z_max_travel raises an exception. If this option is set to True, only a warning is issued. |
| **safe_z** | True | str | Z position below which the needle can hit vials or other objects.Specify as a string including units (metric). |
| **vial_top_z** | True | str | Z position corresponding to the top of the vials.Specify as a string including units (metric). |
| **needle_length** | True | str | Length of the needle mounted on the sampler.Specify as a string including units (metric). |
| **ignore_safe_z** | False | bool | Set to True to allow horizontal movements below the safe height. |
| **locations** | False | dict | 
            Locations specify special positions for the handler, such as vial holders and injection ports.
            This option must be specified in the config file as a dict of location_name -> data pairs.
            Data is a dictionary itself, which must specify:
             - type: "type"
                At the moment, "injection_port" and "holder" are supported.
             - position: {"x": "10.0mm", "y": "10.0mm" (, "z": "10.0mm")}
                Use SI units: mm, cm ecc...
                z position is only used for injection port.
             - shape: "shape"
                This is only for holders. It must match a holder type from the 'sample_holder_types' config file.
            Example:
            "setup": {
              "locations": {
                "injection_flow": {
                  "type": "injection_port",
                  "position": {
                    "x": "170.25mm",
                    "y": "278.5mm",
                    "z": "-60mm"
                  }
                },
                "holder_A": {
                  "type": "holder",
                  "position": {
                    "x": "132.5mm",
                    "y": "38.25mm"
                  },
                  "shape": "vial_GC_4ml_4x4"
                },
             |
| **sampling_pump** | False | str | Identifier name of the syringe pump connected to this sampler. |
