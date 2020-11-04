(function (exports) {
    "use strict";


    var margin = {top: 20, right: 20, bottom: 20, left: 20};
    var height = 120 - margin.top - margin.bottom;
    var profiler_stack = [];
    var ref;
    var brush;
    var tr = 0;
    var handle_width = 10



     exports.visualize = function (container, data_profile, taxon , species){

         if (!data_profile) return;

        var filter_data = [];
         var width = container.offsetWidth - margin.left - margin.right;

        $.each(data_profile, function (idx, val) {

            if (val === 1) {
                filter_data.push(idx);
            }

        });


        var _root = [];
        var _200 = [];
        var _50 = [];

        $.each(taxon, function (level, ltax) {

            if (level == 'root') {

                $.each(ltax, function (name, idx) {
                    _root.push({'idx': idx[0], 'taxon': name});
                })
            }

            else if (level == '50') {

                $.each(ltax, function (name, idx) {
                    _50.push({'idx': idx[0], 'taxon': name});
                })
            }

            else if (level == '200') {

                $.each(ltax, function (name, idx) {
                    _200.push({'idx': idx[0], 'taxon': name});
                })
            }

        });

        var sp_array = []
        $.each(species, function (idx, name) {
            sp_array.push({'idx': idx, 'name': name});
        })


        var data_taxon = function (zoom_level) {


            if (zoom_level > 20) {
                return _50
            }
            else if (zoom_level > 5) {
                return _200
            }
            else {
                return _root
            }
        }

        var zoom = d3.zoom()
        .scaleExtent([1, Infinity])
        .translateExtent([[0, 0], [width, height]])
        .extent([[0, 0], [width, height]])
        .on("zoom", zoomed);

        function zoomed() {
        if (d3.event.sourceEvent && d3.event.sourceEvent.type === "brush") return; // ignore zoom-by-brush



        var e = d3.event.transform;

              x.range([handle_width, width-handle_width ]
                    .map(d => e.applyX(d)));

                svg.selectAll(".bars rect")
                    .attr("x", function (d) {
                        return x(d)
                    })
                    .attr("width", x.bandwidth());

                svg.selectAll(".x-axis").call(xAxis).selectAll("text")
                    .style("text-anchor", "start")
                    .style("font-style",function (d) {return e.k > 5 ? "italic" : "normal"})
                    .style("font-weight",function (d) {return e.k <= 5 ? "bold" : "plain"})
                    .style("text-anchor", "start")

}


        var svg = d3.select(container).append("svg")
            .style("width", width + 'px')
            .attr("viewBox", [0, 0, width, height])
            .attr("class" ,"zoom")
            .call(zoom)
            .on("mousedown.zoom", null)

        var x = d3.scaleBand()
            .domain(data_profile.map(function (d, i) {
                return i
            }))
            .range([handle_width, width-handle_width ])
            .padding(0.1)


        var y = d3.scaleLinear()
            .domain([0, d3.max(data_profile, d => d)]).nice()
            .range([height - margin.bottom, margin.top])

        var xAxis = g => g
            .attr("transform", `translate(0,${height - margin.bottom})`)
            .call(d3.axisBottom(x)
                .tickValues(data_taxon(d3.zoomTransform(svg.node()).k).map(function (d) {
                    return d.idx
                }))
                .tickFormat(function (d) {
                    var result = data_taxon(d3.zoomTransform(svg.node()).k).find(obj => {
                        return obj.idx === d
                    });
                    return result.taxon;
                }));


        var yAxis = g => g
            .attr("transform", `translate(${margin.left},0)`)
            .call(d3.axisLeft(y))
            .call(g => g.select(".domain").remove())

        var color_scale = d3.scaleLinear()
            .domain(data_taxon(d3.zoomTransform(svg.node()).k)
                .map(function (d) {
                    return d.idx
                }))
            .range(["green", "blue", "red"]);

        // Define the div for the tooltip
        const div = d3
            .select('body')
            .append('div')
            .attr('class', 'tooltip')
            .style('opacity', 0);

        svg.append("g")
            .attr("class", "bars")
            .selectAll("rect")
            .data(filter_data)
            .join("rect")
            .attr("x", function (d) {
                return x(d)
            })
            .attr("y", d => y(1))
            .attr("fill", function (d) {
                return color_scale(d)
            })
            .attr("height", d => y(0) - y(1))
            .attr("width", x.bandwidth())
            .on('mouseover',
                function (d) {


                    div.transition().duration(200).style('opacity', 0.9);
                    div.html(sp_array.find(obj => {
                        return obj.idx === d
                    }).name)
                        .style('left', d3.event.pageX + 'px')
                        .style('top', d3.event.pageY - 28 + 'px');
                })
            .on('mouseout', () => {
                div
                    .transition()
                    .duration(500)
                    .style('opacity', 0);
            });

        svg.append("g")
            .attr("class", "x-axis")
            .call(xAxis)
            .selectAll("text")
            .style("font-style", function (d) {
                return d3.zoomTransform(svg.node()).k > 5 ? "italic" : "normal"
            })
            .style("font-weight", function (d) {
                return d3.zoomTransform(svg.node()).k <= 5 ? "bold" : "plain"
            })
            .style("text-anchor", "start")


         svg.on("wheel.zoom", null);


        svg.node();


        return {'svg': svg, 'x': x, 'xAxis': xAxis, 'color_scale': color_scale, 'zoom':zoom};

     };


     exports.bind_zoom = function (ref, container_overview, profiler_stack){


         var svg = ref['svg']
         var x = ref['x']
         var width = container_overview.offsetWidth - margin.left - margin.right;
         var xt = [handle_width,width - handle_width]
         var brush_xt = [[handle_width, margin.top], [width - handle_width, height - margin.bottom]]



         brush = d3.brushX()
            .extent(brush_xt)
             .on("brush", function(d) {
                brushing();
            })
            .on("end", function(d) {
                brushed();
            })

         var brush_g = svg.append("g")
            .attr("class", "brush").call(brush)
            .call(brush.move, x.range())

         var brush_handle = brush_g.selectAll(".handle--custom")
            .data([{type: "w"}, {type: "e"}]).enter().append("path")
            .attr("class", "handle--custom")
            .attr("stroke", "#000")
            .attr("cursor", "ew-resize")
            .attr("d", function (d) {

                var e = +(d.type === "e"),
                x = e ? 1 : -1,
                y = height -2*margin.bottom  ;
            return "M" + (.5 * x) + "," + y + "A6,6 0 0 " + e + " " + (6.5 * x) + "," + (y + 6) + "V" + (2 * y - 6) + "A6,6 0 0 " + e + " " + (.5 * x) + "," + (2 * y) + "Z" + "M" + (2.5 * x) + "," + (y + 8) + "V" + (2 * y - 8) + "M" + (4.5 * x) + "," + (y + 8) + "V" + (2 * y - 8);
        });


         svg.selectAll(".handle--custom").attr("transform", function (d, i) {
                        return "translate(" + xt[i]  + "," + - margin.bottom  + ")";
                    });


        function brushing() {

            if (d3.event.sourceEvent && d3.event.sourceEvent.type === "zoom") return; // ignore brush-by-zoom

            var s = d3.event.selection

            svg.selectAll(".handle--custom").attr("transform", function (d, i) {
                        return "translate(" + s[i]  + "," + - margin.bottom  + ")";
                    });


        }

        function brushed() {

            const selection = d3.event.selection;
            if (!d3.event.sourceEvent || !selection) return;

            if (d3.event.sourceEvent && d3.event.sourceEvent.type === "zoom") return; // ignore brush-by-zoom

            var s = d3.event.selection
            var current_ratio = d3.zoomTransform(ref.svg.node()).k
            var ratio = width  / (s[1] - s[0])
            var sc =  current_ratio * ratio
             tr -= s[0]/current_ratio


            if (current_ratio > 1) {
                $("#resetbutton").show()
            }
            else {$("#resetbutton").hide()}




            console.log(current_ratio)
            console.log(ratio)
            console.log(tr)


            $.each(profiler_stack, function (idx, chart_e) {

                chart_e.svg.call(chart_e.zoom.transform, d3.zoomIdentity.scale(sc).translate(tr, 0));
                chart_e.svg.on("wheel.zoom", null);

            })

            svg.call(ref.zoom.transform, d3.zoomIdentity.scale( sc).translate(tr, 0));
            svg.on("wheel.zoom", null);

            d3.select(".brush").transition().call(brush.move, xt);

             svg.selectAll(".handle--custom").attr("transform", function (d, i) {
                        return "translate(" + xt[i]  + "," + - margin.bottom  + ")";
                    })


        }


     };


     exports.run = function (data_profile, data_profile_ref, data_taxon, data_species, container_reference_selector, container_profile_selector  ){

        var container_ref = document.querySelector(container_reference_selector);

        container_ref.innerHTML = "";
        ref = exports.visualize(container_ref, data_profile_ref["profile"], data_taxon , data_species,  )

        $.each(data_profile, function (each, value) {

            var td_profile = document.querySelector('[data-uniqueid="' + value.id+'"]').querySelector(container_profile_selector);
            td_profile.innerHTML = "";
            profiler_stack.push(exports.visualize(td_profile, value.profile, data_taxon , data_species ))

        })

        exports.bind_zoom(ref,container_ref, profiler_stack)


         //!\\ see how resize window perform now with table //!\\
    }


    exports.reset = function (){

         tr = 0



             var width = document.querySelector(".fixed-table-header th.profile_cell").offsetWidth - margin.left - margin.right;

             var xt = [margin.left,width - margin.right]


            $.each(profiler_stack, function (idx, chart_e) {

                chart_e.svg.call(chart_e.zoom.transform, d3.zoomIdentity.scale(1).translate(0, 0));
                chart_e.svg.on("wheel.zoom", null);

            })

            ref.svg.call(ref.zoom.transform, d3.zoomIdentity.scale( 1).translate(0, 0));
            ref.svg.on("wheel.zoom", null);

            d3.select(".brush").transition().call(brush.move, xt);

             ref.svg.selectAll(".handle--custom").attr("transform", function (d, i) {
                        return "translate(" + 0  + "," + - margin.bottom  + ")";
                    })




    }



})(this.profile = {});
