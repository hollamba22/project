// Parametric 3-antenna fixture for Intel WiFi Link 5300 / DANT-02SPR-BX.
// Units: millimeters.
//
// Export:
//   1. Set part = "body"; export STL.
//   2. Set part = "guide_lock"; export STL.
//   3. Print one body and one guide_lock for TX, and the same pair for RX.

part = "assembly"; // "assembly", "body", "guide_lock"

$fn = 64;

antenna_count = 3;
antenna_spacing = 62.5;       // 2.4 GHz half wavelength spacing.

side_margin = 22;
body_width = (antenna_count - 1) * antenna_spacing + side_margin * 2;
body_depth = 60;
body_height = 160;            // SMA connector top plate height from floor.

wall = 4;
base_thickness = 6;
top_thickness = 5;
corner_chamfer = 0;

sma_hole_d = 6.8;             // Common SMA bulkhead thread clearance.
sma_washer_d = 12.5;          // Visual/clearance ring only.

antenna_body_d = 8.0;         // DANT-02SPR-BX drawing: OD about 8 mm.
guide_clearance = 0.8;
guide_slot_d = antenna_body_d + guide_clearance;

guide_offset = 55;            // Clamp height above the SMA plate.
guide_bar_thickness = 12;
guide_bar_depth = 24;
guide_width = body_width - 10;
guide_lock_thickness = 5;

post_width = 9;
post_depth = guide_bar_depth;

m3_pilot_d = 2.8;
m3_clearance_d = 3.4;
mount_hole_d = 4.5;           // M4 base mounting clearance.
mount_head_d = 9.0;

show_labels = true;

function antenna_x(i) =
    (i - (antenna_count - 1) / 2) * antenna_spacing;

module antenna_positions() {
    for (i = [0 : antenna_count - 1]) {
        translate([antenna_x(i), 0, 0]) children();
    }
}

module shell_body() {
    difference() {
        translate([-body_width / 2, -body_depth / 2, 0])
            cube([body_width, body_depth, body_height]);

        // Rear-open cavity. Front wall, side walls, base, and top remain.
        translate([
            -body_width / 2 + wall,
            -body_depth / 2 + wall,
            base_thickness
        ])
            cube([
                body_width - 2 * wall,
                body_depth - wall + 2,
                body_height - base_thickness - top_thickness
            ]);
    }
}

module zip_tie_anchor(x) {
    // Low bridge for tying each 1.13 coax before it exits the box.
    translate([x - 10, body_depth / 2 - 22, base_thickness])
    difference() {
        cube([20, 10, 8]);
        translate([3, -1, 2])
            cube([14, 12, 4]);
    }
}

module guide_structure() {
    guide_z_min = body_height + guide_offset - guide_bar_thickness / 2;

    // Two rear-biased side posts keep the front of the guide open for loading antennas.
    for (sx = [-1, 1]) {
        translate([
            sx * (guide_width / 2 - post_width / 2),
            -guide_bar_depth / 2,
            body_height
        ])
            cube([post_width, post_depth, guide_offset + guide_bar_thickness / 2]);
    }

    translate([-guide_width / 2, -guide_bar_depth / 2, guide_z_min])
        cube([guide_width, guide_bar_depth, guide_bar_thickness]);
}

module body_positive() {
    shell_body();

    for (i = [0 : antenna_count - 1]) {
        zip_tie_anchor(antenna_x(i));
    }

    guide_structure();
}

module subtract_sma_holes() {
    antenna_positions() {
        translate([0, 0, body_height - top_thickness - 1])
            cylinder(h = top_thickness + 2, d = sma_hole_d);

        // Shallow top-side washer/nut clearance mark.
        translate([0, 0, body_height - 1.2])
            cylinder(h = 1.4, d = sma_washer_d);
    }
}

module subtract_base_holes() {
    for (sx = [-1, 1], sy = [-1, 1]) {
        translate([
            sx * (body_width / 2 - 14),
            sy * (body_depth / 2 - 12),
            -1
        ])
            cylinder(h = base_thickness + 2, d = mount_hole_d);

        translate([
            sx * (body_width / 2 - 14),
            sy * (body_depth / 2 - 12),
            base_thickness - 2.5
        ])
            cylinder(h = 3, d = mount_head_d);
    }
}

module subtract_guide_slots() {
    guide_z_min = body_height + guide_offset - guide_bar_thickness / 2;

    antenna_positions() {
        // Round antenna seat.
        translate([0, 0, guide_z_min - 1])
            cylinder(h = guide_bar_thickness + 2, d = guide_slot_d);

        // Front-open loading slot.
        translate([
            -guide_slot_d / 2,
            -guide_bar_depth / 2 - 1,
            guide_z_min - 1
        ])
            cube([
                guide_slot_d,
                guide_bar_depth / 2 + 1,
                guide_bar_thickness + 2
            ]);
    }
}

module guide_screw_positions() {
    for (sx = [-1, 1]) {
        translate([sx * (guide_width / 2 - 16), 0, body_height + guide_offset])
            children();
    }
}

module subtract_body_guide_screws() {
    guide_screw_positions() {
        rotate([90, 0, 0])
            cylinder(h = guide_bar_depth + 2, d = m3_pilot_d, center = true);
    }
}

module add_labels() {
    if (show_labels) {
        labels = ["TR1", "TR2", "TR3"];
        for (i = [0 : antenna_count - 1]) {
            translate([antenna_x(i) - 8, -body_depth / 2 + 7, body_height + 0.05])
                linear_extrude(height = 0.7)
                    text(labels[i], size = 6, font = "Liberation Sans:style=Bold");
        }
    }
}

module antenna_mount_body() {
    difference() {
        union() {
            body_positive();
            add_labels();
        }

        subtract_sma_holes();
        subtract_base_holes();
        subtract_guide_slots();
        subtract_body_guide_screws();
    }
}

module guide_lock_bar(standalone = true) {
    lock_z = standalone ? guide_bar_thickness / 2 : body_height + guide_offset;
    lock_y = standalone ? 0 : -guide_bar_depth / 2 - guide_lock_thickness / 2;

    difference() {
        translate([
            -guide_width / 2,
            lock_y - guide_lock_thickness / 2,
            lock_z - guide_bar_thickness / 2
        ])
            cube([guide_width, guide_lock_thickness, guide_bar_thickness]);

        for (sx = [-1, 1]) {
            translate([sx * (guide_width / 2 - 16), lock_y, lock_z])
                rotate([90, 0, 0])
                    cylinder(
                        h = guide_lock_thickness + 2,
                        d = m3_clearance_d,
                        center = true
                    );
        }
    }
}

module assembly_preview() {
    antenna_mount_body();
    color([0.1, 0.1, 0.1, 0.55])
        guide_lock_bar(standalone = false);

    // Transparent antenna centerline preview.
    color([0, 0, 0, 0.35])
        antenna_positions()
            translate([0, 0, body_height])
                cylinder(h = 110, d = antenna_body_d);
}

if (part == "body") {
    antenna_mount_body();
} else if (part == "guide_lock") {
    guide_lock_bar(standalone = true);
} else {
    assembly_preview();
}
