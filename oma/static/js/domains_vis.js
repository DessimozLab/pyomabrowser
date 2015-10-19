/* Script file for domains visualisations, using the D3 library.
 *
 * -- Alex Warwick Vesztrocy 2015
 */

var domain_vis = function () {
    "use strict";

    var domain_vis_func = function (class_of_entries) {
        var hog_members = $(class_of_entries);
        var longest_seq = 0; // Length of longest sequence.
        var hog_size = hog_members.length;
        var mem_proc = 0;

        var domains = [];


        $.each(hog_members, function (each, value) {
            // Check if element already read (function can be fired multiple times)
            if ($(this).hasClass("read")) return;
            $(this).addClass("read");

            // Retreive the entry ID
            var entry_id = $(this).attr('id');

            // Grab the domain annotations
            $.getJSON("/oma/domains/" + entry_id + "/json/", function (data) {
                // Find the longest sequence
                if (data.length > longest_seq) longest_seq = data.length;

                // Store this entry's domain annotations
                var domain = {'entry_id': entry_id, 'data': data};
                domains.push(domain);

                // Only process once we've loaded all of the data.
                // This only works because the JS is run sequentially.
                if (mem_proc < (hog_size - 1)) {
                    mem_proc++;
                } else {
                    // Draw each of the sequences with domain annotations
                    $.each(domains, function (i, d) {
                        var svg_container = d3.select("tr#" + d.entry_id + " td.domain_vis")
                            .append("svg:svg");

                        // Read the height from the CSS
                        var svg_height = $("tr#" + d.entry_id + " td.domain_vis svg").height();

                        // Line length (in %) is relative to the longest sequence.
                        var line_length = String((d.data.length / longest_seq) * 100) + "%";
                        var line_weight = 3;

                        var line = svg_container.append("rect")
                            .classed("sequence", true)
                            .attr("y", (svg_height - line_weight) / 2)
                            .attr("width", line_length)
                            .attr("height", line_weight)
                            .attr("rx", 1) // Rounded corners
                            .attr("ry", 1);

                        // Draw each of the regions
                        $.each(d.data.regions, function (i, region) {
                            var locs = region.location.split(':');

                            if(locs.length === 2) {
                                // Call directly
                                draw_region(region,locs);
                            } else {
                                // Same annotation in multiple regions
                                var new_locs = [];
                                for(var i = 0; i<locs.length; i=i+2) {
                                    new_locs.push(locs.slice(i,i+2));
                                }
                                // Call draw function on each of these locations
                                $.each(new_locs,function(i,loc) {
                                    draw_region(region,loc);
                                });
                            }


                            function draw_region(region,loc) {
                                // Work out the location / size of the annotation
                                var start = String((loc[0] / longest_seq) * 100) + "%";
                                var length = String(((loc[1] - loc[0]) / longest_seq) * 100) + "%";
                                var height = svg_height * 0.65;

                                // Get the class
                                var cathid = region.cath_id.split('.');
                                var class_name = "_" + String(cathid[0]) + "_" + String(cathid[1]);

                                // Create the tooltip
                                var tip = d3.tip()
                                    .attr("class", "domain-info")
                                    .direction('w')
                                    .offset([0, -10])
                                    .html("<h1>" + region.cath_id + "</h1>"
                                    + "<p><strong>CATH Architecture:</strong> "
                                    + region.name + "</p>"
                                    + "<p><strong>Location:</strong> "
                                    + loc[0] + " - " + loc[1] + "</p>"
                                    + "<p><strong>Source:</strong> "
                                    + region.source + "</p>");

                                // Draw the domain
                                svg_container.append("rect")
                                    .classed(class_name, true)
                                    .classed("cath_domain", true)
                                    .attr("x", start)
                                    .attr("y", (svg_height / 2) - height / 2)
                                    .attr("width", length)
                                    .attr("height", height)
                                    .attr("rx", 2.5) // Rounded corners
                                    .attr("ry", 2.5)
                                    .call(tip)  // Setup the tooltip
                                    .on('mouseover', tip.show)
                                    .on('mouseout', tip.hide)
                                    .on('mousedown', function () {
                                        // Open CATH Link in new tab
                                        var url = 'http://www.cathdb.info/version/latest/superfamily/' + region.cath_id;
                                        window.open(url, '_blank')
                                            .focus();
                                    });
                            };
                        });
                    });
                }
            });
        });
    };
    return domain_vis_func;
};

