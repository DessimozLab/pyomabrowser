
(function (exports) {
    "use strict";


    exports.visualize_all = function (class_of_entries, data, attr_name) {

        if(attr_name === undefined){ attr_name = 'id'; }

        console.log(data);

        var start = 0;
        var end = 0;

        $.each(data, function (each, value) {
            if (value.locus_start < start){
                start = value.locus_start;
            }

            if (value.locus_end > end){
                end = value.locus_end;
            }
        });

        var longest_seq = end-start;

        $.each($(class_of_entries), function (each, value) {

            var entry_id = $(this).attr(attr_name),
                container = $(this).find('.exon_vis')[0];
                const dat = data.find(element => element.protid == entry_id);

            exports.visualize_exon(container, dat, longest_seq);
        });



    };

    exports.visualize_exon = function(container, dat, longest_seq) {


                var svg_container = d3.select(container).append("svg:svg");

                // Read the height from the CSS
                var svg_height = parseInt(svg_container.style('height'));

                // Line length (in %) is relative to the longest sequence.

                var line_length = String((dat.seqlen / longest_seq) * 100) + "%";
                var line_weight = 3;

                var line = svg_container.append("rect")
                    .classed("sequence", true)
                    .attr("y", (svg_height - line_weight) / 2)
                    .attr("width", line_length)
                    .attr("height", line_weight)
                    .attr("rx", 1) // Rounded corners
                    .attr("ry", 1);


                /*

                var hashval = function(s) {
                    var hash = 18, i, chr;
                    if (s === undefined || s.length === 0) return hash;
                    for (i = 0; i < s.length; i++) {
                        chr = s.charCodeAt(i);
                        hash = ((hash << 5) - hash) + chr;
                        hash |= 0; // Convert to 32bit integer
                    }
                    return hash;
                };



                // Draw each of the regions
                $.each(data.regions, function (i, region) {
                    var locs = region.location.split(':');
                    locs = locs.map(function (x) {
                        return parseInt(x)
                    });

                    if (locs.length === 2) {
                        // Call directly
                        draw_region(region, locs);
                    } else {
                        // Same annotation in multiple regions
                        var new_locs = [];
                        for (var j = 0; j < locs.length; j += 2) {
                            new_locs.push(locs.slice(j, j + 2));
                        }
                        // Call draw function on each of these locations
                        $.each(new_locs, function (i, loc) {
                            draw_region(region, loc);
                        });
                    }


                    function draw_region(region, loc) {
                        // Work out the location / size of the annotation
                        var start = String((loc[0] / longest_seq) * 100) + "%";
                        var length = String(((loc[1] - loc[0]) / longest_seq) * 100) + "%";
                        var height = svg_height * 0.65;


                        // Get the class
                        var class_name = "_n_a";
                        var base_url = "";
                        if (region.source === "Pfam") {
                            class_name = "_pfam";
                            base_url = "https://pfam.xfam.org/family/";

                        } else if (region.source === "CATH/Gene3D") {
                            var cathid = region.domainid.split('.');
                            class_name = "_" + String(cathid[0]) + "_" + String(cathid[1]);
                            base_url = "http://www.cathdb.info/version/latest/superfamily/"
                        }

                        // Create the tooltip
                        var tip = d3.tip()
                            .attr("class", "domain-info")
                            .direction('w')
                            .offset([0, -10])
                            .html("<h1>" + region.domainid + "</h1>"
                                + "<p><strong>Name:</strong> "
                                + region.name + "</p>"
                                + "<p><strong>Location:</strong> "
                                + loc[0] + " - " + loc[1] + "</p>"
                                + "<p><strong>Source:</strong> "
                                + region.source + "</p>");

                        // Draw the domain
                        var opacity = (Math.abs(hashval(region.domainid)) %19) / 38 + 0.5;
                        var dom = svg_container.append("rect")
                            .classed(class_name, true)
                            .classed("cath_domain", true)
                            .attr("x", start)
                            .attr("opacity", opacity)
                            .attr("y", (svg_height / 2) - height / 2)
                            .attr("width", length)
                            .attr("height", height)
                            .attr("rx", 2.5) // Rounded corners
                            .attr("ry", 2.5);

                        if (region.source === "n/a") {
                            svg_container.append("text")
                                .attr("x", String((loc[1] + loc[0]) / (2 * longest_seq) * 100) + "%")
                                .attr("y", (svg_height / 2) + height / 4)
                                .text("n/a");
                        } else {
                            dom.call(tip)
                                .on('mouseover', tip.show)
                                .on('mouseout', tip.hide)
                                .on('click', function () {
                                    var url = base_url + region.domainid;
                                    window.open(url, '_blank')
                                        .focus();
                                });
                        }


                    }



            });

            */


    };


})(this.exon={});
