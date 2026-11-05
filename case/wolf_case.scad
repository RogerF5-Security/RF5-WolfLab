// RF5 WolfLab Wolf Vent / millimetres / physical fit unverified.
part="print"; // base, lid, print, assembly
pcb_width=18; pcb_length=22.52; pcb_bottom=8; pcb_thickness=1.6;
base_height=15; floor_thickness=1.6; lid_thickness=1.6;
fit_gap=.30; lip_height=2.4; lip_wall=1.2;
outline=[[-7,-20],[7,-20],[16,-10],[17,9],[16,24],[6,16],[-6,16],[-16,24],[-17,9],[-16,-10]];
inner=[[-6.2,-18.4],[6.2,-18.4],[14.4,-9.3],[15.4,8.9],[14.6,20.9],[6.5,14.4],[-6.5,14.4],[-14.6,20.9],[-15.4,8.9],[-14.4,-9.3]];
module rect(x,y,w,h,z,height){translate([x-w/2,y-h/2,z])cube([w,h,height]);}
module base(){difference(){union(){
 linear_extrude(floor_thickness)polygon(outline);
 linear_extrude(base_height)difference(){polygon(outline);polygon(inner);}
 for(x=[-4.8,4.8],y=[-9,9])rect(x,y,2.4,2.4,0,pcb_bottom);
 for(x=[-9.8,9.8],y=[-5,4])rect(x,y,.8,3,0,pcb_bottom+pcb_thickness);
 for(y=[-(pcb_length/2+.8),pcb_length/2+.8])rect(0,y,4,.8,0,pcb_bottom);
 }
 rect(0,-20,14,19.2,8,base_height);
 for(y=[-6,-2,2,6,10])rect(0,y,6,1.6,-.01,floor_thickness+.02);
 for(x=[-17,17],y=[-6,-1,4,9])rect(x,y,8,2,3.2,3.2);
}}
module lid(){difference(){union(){
 linear_extrude(lid_thickness)polygon(outline);
 translate([0,0,lid_thickness])linear_extrude(lip_height)difference(){
  offset(delta=-fit_gap)polygon(inner);offset(delta=-(fit_gap+lip_wall))polygon(inner);
 }
 }
 for(s=[-1,1])translate([0,0,-.01])linear_extrude(lid_thickness+.02)scale([s,1])polygon([[2,3.6],[11,6],[11,4.2],[3,1.8]]);
 rect(0,-8,20,8,-.01,lid_thickness+.02);
 for(y=[9,12])rect(0,y,12,1.6,-.01,lid_thickness+.02);
}}
if(part=="base")base();
else if(part=="lid")lid();
else if(part=="assembly"){base();translate([0,0,base_height+lid_thickness])rotate([0,180,0])lid();}
else{translate([-24,0,0])base();translate([24,0,0])lid();}
