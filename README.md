# CDT-doodlebob
My cyberdefense competition red team tool: doodlebob.

Doodlebob.exe is an annoyance tool used to -- you guessed it -- annoy blue teams. The primary function of Doodlebob is to close GUI windows in 20 minute intervals (formerly 10 but grey team advised 20). I added in textbox popups at 5 minute intervals just for fun. 

The ansible script copies doodlebob.exe over to a somewhat hidden folder in windows32 directory, at C:\Windows\System32\Recovery\tmp\ddlbb.exe. It also creates a timed task for the program to run about halfway through the first competition day, listed as "timesyncTask" and a similar description. 

This was my first tool so I hope it works out. 
