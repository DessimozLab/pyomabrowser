(function (exports) {
    "use strict";


    var margin = {top: 20, right: 20, bottom: 20, left: 20};
    var margin2 = {top: 5, right: 20, bottom: 15, left: 20};
    var attr_name = 'id';
    var class_of_entries = ".profile_vis";
    var class_ref = ".profile_vis_ref";
    var class_overview = ".overview";
    var minimap_factor = null;

    exports.visualize_all = function (profile_data, taxon_data, species_data, ref_profile_data) {

        var _root = [];
        var _200 = [];
        var _50 = [];
        var array_chart = []
        var width, height

        $.each(taxon_data, function (level, ltax) {

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

        var minimap = exports.run_header(ref_profile_data, taxon_data, species_data, _root)

        $.each($(class_of_entries), function (each, value) {

            // Retreive the entry ID
            var entry_id = $(this).attr(attr_name);
            var data_item = profile_data[entry_id];
            var container = this;


            width = container.offsetWidth - margin.left - margin.right,
                height = 120 - margin.top - margin.bottom;

            container.innerHTML = "";

            var chart_data = exports.run_profile_vis(container, data_item, taxon_data, species_data, margin, width, height);

            array_chart.push(chart_data)

        });

        var container_ref = document.getElementById("Reference");

        var container = document.getElementById("Reference");


        container.innerHTML = "";

        var chart_data = exports.run_profile_vis(container, ref_profile_data['Reference'], taxon_data, species_data, margin, width, height);

        array_chart.push(chart_data)

        exports.bind_brush_and_zoom(minimap, array_chart)





    };

    exports.run_header = function (ref_profile_data, taxon_data, species_data, _root) {

        // Reference Profile

        var container_ref = document.getElementById("Reference");

        var widthr = container_ref.offsetWidth - margin.left - margin.right, heightr = 120 - margin.top - margin.bottom;

        // MINIMAP

        var container_overview = document.getElementById("overview");

        var width = container_overview.offsetWidth - margin.left - margin.right,
            height = 60 - margin2.top - margin2.bottom;
        var data_taxon = _root

        //
        var data_profile = ref_profile_data["Reference"];


        var filter_data = []

        $.each(data_profile, function (idx, val) {

            if (val === 1) {
                filter_data.push(idx);
            }

        });

        //
        var svg = d3.select(container_overview).append("svg")
            .attr("viewBox", [0, 0, width, height])

        //
        var x = d3.scaleBand()
            .domain(data_profile.map(function (d, i) {
                return i
            }))
            .range([margin2.left, width - margin2.right])
            .padding(0.1)

        //
        var y = d3.scaleLinear()
            .domain([0, 1])
            .range([height - margin2.bottom, margin2.top])

        //
        var xAxis = g => g
            .attr("transform", `translate(0,${height - margin2.bottom})`)
            .call(d3.axisBottom(x)
                .tickValues(data_taxon.map(function (d) {
                    return d.idx
                }))
                .tickFormat(function (d) {
                    var result = data_taxon.find(obj => {
                        return obj.idx === d
                    });
                    return result.taxon;
                }));

        var yAxis = g => g
            .attr("transform", `translate(${margin2.left},0)`)
            .call(d3.axisLeft(y))
            .call(g => g.select(".domain").remove())

        //
        var color_scale = d3.scaleLinear()
            .domain(data_taxon.map(function (d) {
                return d.idx
            }))
            .range(["green", "blue", "red"]);


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

        svg.append("g")
            .attr("class", "x-axis")
            .call(xAxis)
            .selectAll("text")
            .style("font", "8px times")
            .style("font-weight", "bold")
            .style("text-anchor", "start")

        svg.node();

        minimap_factor = widthr/width;

            return [svg, x]

    }

    exports.bind_brush_and_zoom = function (minimap, array_chart) {



        var svg = minimap[0]
        var x = minimap[1]

        var container_overview = document.getElementById("overview");

        var width = container_overview.offsetWidth - margin.left - margin.right,
            height = 60 - margin2.top - margin2.bottom;


        var brush_xtent = [[margin2.left, margin2.top], [width - margin2.right, height - margin2.bottom]]

        var brush = d3.brushX()
            .extent(brush_xtent)
            .on("brush end", function () {
                var s = d3.event.selection

                d3.select(this).selectAll(".handle--custom").attr("transform", function (d, i) {
                        return "translate(" + s[i] + "," + -margin2.bottom + ")";
                    });

                brushed(s, array_chart[0])
            });

        var brushResizePath = function (d) {
            var e = +(d.type === "e"),
                x = e ? 1 : -1,
                y = (height -margin2.bottom -margin2.bottom)*2 ;
            return "M" + (.5 * x) + "," + y + "A6,6 0 0 " + e + " " + (6.5 * x) + "," + (y + 6) + "V" + (2 * y - 6) + "A6,6 0 0 " + e + " " + (.5 * x) + "," + (2 * y) + "Z" + "M" + (2.5 * x) + "," + (y + 8) + "V" + (2 * y - 8) + "M" + (4.5 * x) + "," + (y + 8) + "V" + (2 * y - 8);
        };

        var gg = svg.append("g")
            .attr("class", "brush").call(brush)
            .call(brush.move, x.range())

            var gh = gg.selectAll(".handle--custom")
            .data([{type: "w"}, {type: "e"}]).enter().append("path")
            .attr("class", "handle--custom")
            .attr("stroke", "#000")
            .attr("cursor", "ew-resize")
            .attr("d", brushResizePath);


        svg.selectAll(".handle--custom").attr("transform", function (d, i) {
                        return "translate(" + brush_xtent[i][0]  + "," + -margin2.bottom  + ")";
                    });

        function brushed(s, ref_prof) {

            if (d3.event.sourceEvent && d3.event.sourceEvent.type === "zoom") return; // ignore brush-by-zoom
            var s = d3.event.selection

            $.each(array_chart, function (idx, chart_e) {


                chart_e.svg.call(chart_e.zoom.transform, d3.zoomIdentity.scale( (width  / (s[1] - s[0]))).translate(-s[0], 0));

                chart_e.svg.on("wheel.zoom", null);

            })

        }



    }

    exports.run_profile_vis = function (container, data_profile, taxon, species, margin, width, height) {

        if (!data_profile) return;

        var filter_data = []

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

              x.range([margin.left, width - margin.right]
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
            .attr("viewBox", [0, 0, width, height])
            .attr("class" ,"zoom")
            .call(zoom)
            .on("mousedown.zoom", null)

        var x = d3.scaleBand()
            .domain(data_profile.map(function (d, i) {
                return i
            }))
            .range([margin.left, width - margin.right])
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


        svg.node();


        return {'svg': svg, 'x': x, 'xAxis': xAxis, 'color_scale': color_scale, 'zoom':zoom};


    };

})(this.profile = {});
