
(function (exports) {
    "use strict";


    exports.visualize_all = function (class_of_entries, data, attr_name) {

        if(attr_name === undefined){ attr_name = 'id'; }


        // get the start and the end of the gene (same for all isoforms)
        var gene_start = 1000000000000000000000;
        var gene_end = 0;

        $.each(data, function (each, value) {
            if (value.locus_start < gene_start){
                gene_start = value.locus_start;
            }

            if (value.locus_end > gene_end){
                gene_end = value.locus_end;
            }
        });

        //Get the genes length
        var gene_length = gene_end-gene_start;

        $.each($(class_of_entries), function (each, value) {

            var entry_id = $(this).attr(attr_name), container = $(this).find('.exon_vis')[0];
            const exon_data = data.find(element => element.protid == entry_id);

            exports.visualize_exon(container, exon_data, gene_start, gene_end, gene_length);
        });



    };

    exports.visualize_exon = function(container, exon_data, gene_start, gene_end, gene_length) {


                // Create svg container
                var svg_container = d3.select(container).append("svg:svg");
                var svg_height = parseInt(svg_container.style('height'));
                var line_weight = 20;

                var line = svg_container.append("rect")
                    .classed("sequence", true)
                    .attr("y", (svg_height - line_weight) / 2)
                    .attr("width", "100%")
                    .attr("height", line_weight);


                // Compute the ratio between line pixel and gene position
                var px_factor = gene_length/line.node().getBoundingClientRect().width

                // Draw each of the regions
                $.each(exon_data.exons, function (i, exon) {


                    var height = svg_height * 0.65;
                    var exon_len = (exon.end - exon.start )/px_factor;
                    var exon_start = (exon.start-gene_start)/px_factor;

                    // Create the tooltip
                        var tip = d3.tip()
                            .attr("class", "exon-info")
                            .direction('w')
                            .offset([0, -10])
                            .html( "<p><strong>Exon start:</strong> "
                                + exon.start + "</p>"
                                + "<p><strong>Exon end:</strong> "
                                + exon.end + "</p>");


                    var dom = svg_container.append("rect")
                            .attr("x", exon_start)
                            .attr("opacity", 1)
                            .classed("rect_exon", true)
                            .attr("y", (svg_height / 2) - height / 2)
                            .attr("width", exon_len)
                            .attr("height", height);

                    dom.call(tip).on('mouseover', tip.show).on('mouseout', tip.hide);
            });
    };


})(this.exon={});
