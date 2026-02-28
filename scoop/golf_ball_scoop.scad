// Golf Ball Retriever Scoop for Ultron Rover
// Designed by Ultron - February 2026
// For Freenove 4WD Smart Car Kit + SG90 Servo

// === PARAMETERS ===
// Golf ball specs
ball_diameter = 42.67;  // Standard golf ball diameter (mm)
ball_radius = ball_diameter / 2;

// Scoop dimensions (generous for forgiving capture)
scoop_width = 70;       // 70mm wide (~2.75") - forgiving alignment
scoop_length = 80;      // 80mm long - enough to fully capture ball
scoop_depth = 25;       // How deep the channel is
wall_thickness = 3;     // Wall thickness

// Mounting plate
mount_length = 40;      // Extension for chassis mounting
mount_width = scoop_width;
mount_thickness = 4;
mount_hole_diameter = 3.5;  // M3 screws
mount_hole_spacing = 30;    // Holes 30mm apart

// Servo horn mount
servo_horn_width = 8;
servo_horn_length = 20;
servo_horn_hole = 2;    // Servo horn screw hole

// Back wall (prevents ball from rolling out)
back_wall_height = 20;

// === MODULES ===

// The curved scoop channel
module scoop_channel() {
    difference() {
        // Outer shell
        translate([0, 0, 0])
        hull() {
            // Front lip (curved entry)
            translate([0, 0, 0])
                cube([scoop_width, wall_thickness, wall_thickness]);
            // Back of scoop
            translate([0, scoop_length - wall_thickness, scoop_depth])
                cube([scoop_width, wall_thickness, wall_thickness]);
        }
        
        // Inner cutout (the channel)
        translate([wall_thickness, -1, wall_thickness])
        hull() {
            translate([0, 0, 0])
                cube([scoop_width - 2*wall_thickness, wall_thickness + 1, 0.1]);
            translate([0, scoop_length - wall_thickness, scoop_depth - wall_thickness])
                cube([scoop_width - 2*wall_thickness, wall_thickness + 1, 0.1]);
        }
    }
}

// Curved cradle for the ball (sits at back of scoop)
module ball_cradle() {
    translate([scoop_width/2, scoop_length - ball_radius - 5, scoop_depth])
    difference() {
        // Cradle cylinder
        rotate([0, 90, 0])
            cylinder(h = scoop_width - 2*wall_thickness, r = ball_radius + wall_thickness, center = true, $fn = 64);
        
        // Carve out ball space
        rotate([0, 90, 0])
            cylinder(h = scoop_width, r = ball_radius + 1, center = true, $fn = 64);
        
        // Cut off bottom half
        translate([0, 0, -ball_radius - wall_thickness])
            cube([scoop_width + 10, ball_diameter + 10, ball_diameter], center = true);
        
        // Cut off top (open top for ball entry)
        translate([0, 0, ball_radius])
            cube([scoop_width + 10, ball_diameter + 10, ball_diameter], center = true);
    }
}

// Back wall to prevent ball rollout
module back_wall() {
    translate([0, scoop_length - wall_thickness, 0])
        cube([scoop_width, wall_thickness, back_wall_height + scoop_depth]);
}

// Side walls for guidance
module side_walls() {
    // Left wall
    hull() {
        cube([wall_thickness, scoop_length, wall_thickness]);
        translate([0, scoop_length - wall_thickness, scoop_depth + back_wall_height])
            cube([wall_thickness, wall_thickness, wall_thickness]);
    }
    
    // Right wall
    translate([scoop_width - wall_thickness, 0, 0])
    hull() {
        cube([wall_thickness, scoop_length, wall_thickness]);
        translate([0, scoop_length - wall_thickness, scoop_depth + back_wall_height])
            cube([wall_thickness, wall_thickness, wall_thickness]);
    }
}

// Mounting plate with screw holes
module mounting_plate() {
    difference() {
        // Plate
        translate([0, scoop_length, 0])
            cube([mount_width, mount_length, mount_thickness]);
        
        // Screw holes (4 holes in a rectangle)
        hole_x_offset = (mount_width - mount_hole_spacing) / 2;
        hole_y_offset = (mount_length - mount_hole_spacing) / 2;
        
        for (x = [hole_x_offset, mount_width - hole_x_offset]) {
            for (y = [hole_y_offset, mount_length - hole_y_offset]) {
                translate([x, scoop_length + y, -1])
                    cylinder(h = mount_thickness + 2, d = mount_hole_diameter, $fn = 32);
            }
        }
    }
}

// Servo horn attachment point
module servo_mount() {
    translate([scoop_width/2 - servo_horn_width/2, scoop_length + mount_length, 0]) {
        difference() {
            // Horn mount block
            cube([servo_horn_width, servo_horn_length, mount_thickness + 5]);
            
            // Servo horn screw hole
            translate([servo_horn_width/2, servo_horn_length/2, -1])
                cylinder(h = mount_thickness + 7, d = servo_horn_hole, $fn = 32);
        }
    }
}

// Floor of the scoop (curved ramp)
module scoop_floor() {
    translate([wall_thickness, 0, 0])
    hull() {
        // Front edge (at ground level)
        cube([scoop_width - 2*wall_thickness, wall_thickness, wall_thickness]);
        
        // Back edge (raised to cradle height)
        translate([0, scoop_length - wall_thickness - 10, scoop_depth - wall_thickness])
            cube([scoop_width - 2*wall_thickness, wall_thickness, wall_thickness]);
    }
}

// === MAIN ASSEMBLY ===
module golf_ball_scoop() {
    color("DodgerBlue") {
        scoop_floor();
        side_walls();
        back_wall();
        mounting_plate();
        servo_mount();
    }
    
    // Show ball for reference (comment out for export)
    // %translate([scoop_width/2, scoop_length - ball_radius - 10, scoop_depth + ball_radius])
    //     sphere(d = ball_diameter, $fn = 64);
}

// Render it!
golf_ball_scoop();

// === EXPORT INFO ===
// To export STL:
// 1. Open in OpenSCAD
// 2. Press F6 to render
// 3. File > Export > Export as STL
//
// Print settings recommended:
// - Layer height: 0.2mm
// - Infill: 20%
// - Supports: Yes (for curved areas)
// - Material: PLA or PETG
