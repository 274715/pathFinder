G21 ; Set units to mm
G90 ; Use absolute positioning
G28 ; Home all axes
G0 X150.0 Y300.0
; Move from e2
G0 X150.0 Y200.0
 ; Move to e4
G0 X150.0 Y50.0
; Move from e7
G0 X150.0 Y150.0
 ; Move to e5
G0 X50.0 Y350.0
; Move from g1
G0 X100.0 Y250.0
 ; Move to f3
G0 X300.0 Y0.0
; Move from b8
G0 X250.0 Y100.0
 ; Move to c6
M104 S0 ; Turn off extruder
M140 S0 ; Turn off heated bed
M107 ; Turn off fan
M84 ; Disable motors