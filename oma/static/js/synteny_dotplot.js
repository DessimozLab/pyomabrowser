var dotplot_theme;

dotplot_theme = function () {

    function DotPlot(container_id, url_json, genome1, genome2, chromosome1, chromosome2) {

        /////////////
        // METHODS //
        /////////////

        this.between = function (x, min, max) {
            return x >= min && x <= max;
        };
        this.sortNumber = function (a, b) {
            return a - b;
        };

        // UI
        this.create_containers = function (container) {

            // This should be updated and reused because for now I make them manually in the html

            // create plot div
            cdotplot = document.createElement('div');
            cdotplot.id = "plot_div";
            cdotplot.style.width = "100%";
            container.appendChild(cdotplot);

            // create legend div
            chist_metric = document.createElement('div');
            chist_metric.id = "hist_metric";
            chist_metric.style.width = "100%";
            container.appendChild(chist_metric);


        };
        this.set_up_brush_action_setting = function () {

            function update_action_dropdown(selected_action){
                if (selected_action === 'ba-select' || selected_action === 's') {
                    brush_action = 'select';
                    d3.select('#brush_ok_zoom').classed('hidden', true);
                    d3.select('#brush_ok_select').classed('hidden', false);
                    d3.select('#brush_ok_pan').classed('hidden', true);

                }
                else if (selected_action === 'ba-zoom') {
                    brush_action = 'zoom';
                    d3.select('#brush_ok_zoom').classed('hidden', false);
                    d3.select('#brush_ok_select').classed('hidden', true);
                    d3.select('#brush_ok_pan').classed('hidden', true);
                }
                else if (selected_action === 'ba-pan' || selected_action === 'a') {
                    brush_action = 'pan';
                    d3.select('#brush_ok_pan').classed('hidden', false);
                    d3.select('#brush_ok_zoom').classed('hidden', true);
                    d3.select('#brush_ok_select').classed('hidden', true)
                }
            }

            genedata_picker = d3.select("#action_dropdown").selectAll(".action_dropdown-li").on('click', function () {
                update_action_dropdown(this.id);
            });


            document.onkeypress = function(evt) {
                evt = evt || window.event;
                var charCode = evt.keyCode || evt.which;
                var charStr = String.fromCharCode(charCode);
                update_action_dropdown(charStr);
            };



        };

        //dotplot
        this.add_legend_color = function () {

            svg_dotplot.selectAll(".legend").remove();
            svg_dotplot.selectAll(".legend rect").remove();
            svg_dotplot.selectAll(".legend text").remove();
            svg_dotplot.selectAll(".color_legend_text").remove();


            // Add a legend for the color values.
            var legend = svg_dotplot.selectAll(".legend")
                .data(color_threshold.ticks(10).slice(1).reverse())
                .enter().append("g")
                .attr("class", "legend")
                .attr("visibility", "visible")
                .attr("transform", function (d, i) {
                    return "translate(" + (width - 30) + "," + (50 + i * 10) + ")";
                });

            legend.append("rect")
                .attr("width", 10)
                .attr("height", 10)
                .style("fill", color_threshold);

            legend.append("text")
                .attr("x", 15)
                .attr("y", 6)
                .attr("dy", ".35em")
                .style("font-size", "8px")
                .style("text-anchor", "start")
                .text(function (d) {
                    return d
                });

            svg_dotplot.append("text")
                .attr("class", "label color_legend_text")
                .attr("x", width - 20)
                .attr("y", 40)
                .attr("dy", ".35em")
                .style("text-anchor", "middle")
                .text(metric_option.short_name);

        };
        this.update_color_scales = function () {
            var color_domain = [filter_min_distance, filter_max_distance];
            var color_range = ['#90ee90', '#000080'];
            //color_range = ['#ffbdbd', '#e1f7d5'];
            color_threshold = d3.scaleLinear().domain(color_domain).range(color_range);
        };
        this.update_visibility_dot = function () {


            dotplot.update_color_scales();

            svg_dotplot.selectAll("circle")
                .attr('fill', function (d) {
                    return color_threshold(d.distance)
                })
                .attr("visibility", function (d) {

                    var dist = parseInt(d.distance);


                    if (dotplot.between(dist, filter_min_distance, filter_max_distance)) {
                        return "visible";

                    }
                    return "hidden";

                });


            dotplot.add_legend_color()


        };

        // metric histogram
        this.add_color_legend = function (color_threshold, svg_legend) {

            var formatNumber = d3.format(".0f");

            var x_legend = d3.scaleLinear()
                .domain(color_threshold.domain())
                .range([0, 240]);

            var xAxis_legend = d3.axisBottom(x_legend)
                .tickSize(13)
                .tickValues(color_threshold.domain())
                .tickFormat(function (d) {
                    return formatNumber(d)
                });

            var g = svg_legend.append("g");


            g.call(xAxis_legend);

            g.select(".domain")
                .remove();

            g.selectAll("rect")
                .data(color_threshold.range().map(function (color) {
                    var d = color_threshold.invertExtent(color);
                    if (d[0] === null) d[0] = x_legend.domain()[0];
                    if (d[1] === null) d[1] = x_legend.domain()[1];
                    return d;
                }))
                .enter().insert("rect", ".tick")
                .attr("height", 8)
                .attr("x", function (d) {
                    return x_legend(d[0]);
                })
                .attr("width", function (d) {
                    return x_legend(d[1]) - x_legend(d[0]);
                })
                .attr("fill", function (d) {
                    return color_threshold(d[0]);
                });

            g.append("text")
                .attr("fill", "#000")
                .attr("font-weight", "bold")
                .attr("text-anchor", "start")
                .attr("y", -6)
                .text("Phylogenetic distance");
        };
        this.calculate_frequencies = function (arr) {

            var a = [], b = [], prev = null;

            arr.sort(dotplot.sortNumber);
            for (var i = 0; i < arr.length; i++) {
                if (arr[i] !== prev) {
                    a.push(arr[i]);
                    b.push(1);
                } else {
                    b[b.length - 1]++;
                }
                prev = arr[i];
            }

            return [a, b];
        };
        this.compute_histogram_metric = function (data) {


            var data_slice_metric = [];

            data.forEach(function (d) {
                data_slice_metric.push(parseInt(d[metric_option.accessor]));
            });

            // make the histogram data
            var val = [], freq = [], prev = null;

            data_slice_metric.sort(dotplot.sortNumber);
            for (var i = 0; i < data_slice_metric.length; i++) {
                if (data_slice_metric[i] !== prev) {
                    val.push(data_slice_metric[i]);
                    freq.push(1);
                } else {
                    freq[freq.length - 1]++;
                }
                prev = data_slice_metric[i];
            }

            // end make the histogram data

            var hist_color = [];

            for (var i = 0; i < val.length; i++) {
                hist_color.push({'value': val[i], 'freq': freq[i]})
            }

            return hist_color;

        };
        this.update_picked_datapoint = function (datapoint) {
            picked_datapoint = datapoint;
            svg_dotplot.selectAll("circle")
                .classed("picked", function (d) {
                    return (d.entry_1.omaid === picked_datapoint.entry_1.omaid &&
                    d.entry_2.omaid === picked_datapoint.entry_2.omaid);
                });
        };

        ///////////////
        // VARIABLES //
        ///////////////

        // This (DotPlot) will be override in the function scope, we keep it somewhere.
        var dotplot = this;

        // container with dotplot div and legend color div
        var cviewer = document.getElementById(container_id), cdotplot, chist_metric;
        //dotplot.create_containers(cviewer);

        // variable for the dotplot brush action
        var brush_action = 'pan';
        d3.select('#brush_ok_pan').classed('hidden', false);
        dotplot.set_up_brush_action_setting();

        // selection variable
        var filter_max_distance, filter_min_distance;
        var selected_pairs = [];
        var picked_datapoint = null;  // picked from table

        // margin to apply on the dotplot svg
        var margin_plot = {top: 20, right: 50, bottom: 20, left: 50};

        // size of the dotplot svg
        var size_plot = {width: cviewer.offsetWidth - margin_plot.right, height: 450};

        // the svg that countains the dotplot
        var svg_dotplot = d3.select("#plot_div").append("svg")
            .attr("width", size_plot.width)
            .attr("height", size_plot.height)
            .append("g")
            .attr("transform", "translate(" + margin_plot.left + "," + margin_plot.top + ")");

        // size of the legend svg
        var size_legend = {width: size_plot.width, height: 80};

        // the svg that countains the legend
        var svg_hist = d3.select("#hist_metric").append("svg")
            .attr("width", size_legend.width)
            .attr("height", size_legend.height)
            .append("g")
            .attr("transform", "translate(" + margin_plot.left + "," + 0 + ")");

        var width = size_plot.width - margin_plot.left - margin_plot.right,
            height = size_plot.height - margin_plot.top - margin_plot.bottom;

        var metric_option = {long_name: 'Phylogenetic Distance', short_name: 'Distance', accessor: 'distance'};

        // data accession should be  done with function for the metrix, the x and y value!


        d3.json(url_json, function (error, data) {

            var hist_color = dotplot.compute_histogram_metric(data);

            // data boundaries
            var min_distance = d3.min(data, function (d) {
                return parseFloat(d[metric_option.accessor]);
            });
            var max_distance = d3.max(data, function (d) {
                return parseFloat(d[metric_option.accessor]);
            });
            var min_position_x = d3.min(data, function (d) {
                return d.entry_1.locus[0];
            });
            var max_position_x = d3.max(data, function (d) {
                return d.entry_1.locus[0];
            });
            var min_position_y = d3.min(data, function (d) {
                return d.entry_2.locus[0];
            });
            var max_position_y = d3.max(data, function (d) {
                return d.entry_2.locus[0];
            });

            // set the inital filtering boundaries to extremum values
            filter_max_distance = max_distance;
            filter_min_distance = min_distance;

            dotplot.update_color_scales();

            // scaling of data on axis
            var x0 = [min_position_x, max_position_x],
                y0 = [min_position_y, max_position_y],
                x = d3.scaleLinear().domain(x0).range([0, width]),
                y = d3.scaleLinear().domain(y0).range([height, 0]);


            // x axis
            var xAxis = d3.axisBottom(x)
                .ticks(12)
                .tickFormat(function (d) {
                    return d3.formatPrefix(".1", max_position_x)(d) + 'b';
                });

            // y axis
            var yAxis = d3.axisLeft(y)
                .ticks(12 * height / width)
                .tickFormat(function (d) {
                    return d3.formatPrefix(".1", max_position_y)(d) + 'b';
                });

            // brush object
            var brush_plot = d3.brush()
                    .filter(function () {
                        return !(brush_action == 'pan')
                    })
                    .on("end", brushended_plot),
                idleTimeout,
                idleDelay = 350;

            // Define the div for the tooltip
            var tooltip_div = d3.select("body").append("div")
                .attr("class", "tooltip")
                .style("opacity", 0);

            // g brush element
            var gbrush_plot = svg_dotplot.append("g")
                .attr("class", "brush")
                .call(brush_plot);

            // clip element to restrict drawing circles inside the axis boundary
            var clip = gbrush_plot.append("defs").append("svg:clipPath")
                .attr("id", "clip")
                .append("svg:rect")
                .attr("id", "clip-rect")
                .attr("x", "0")
                .attr("y", "0")
                .attr('width', width)
                .attr('height', height);

            // dots elements
            var gcircles = svg_dotplot
                .append("g")
                .attr("clip-path", "url(#clip)")
                .selectAll("circle")
                .attr("class", "circle")
                .data(data)
                .enter().append("circle")
                .attr("cx", function (d) {
                    return x(d.entry_1.locus[0]);
                })
                .attr("cy", function (d) {
                    return y(d.entry_2.locus[0]);
                })
                .attr("fill", function (d) {
                    return color_threshold(d[metric_option.accessor])
                })
                //.attr('r', function(d){ return currentZoom ? 2.5  / currentZoom.k : 2.5})
                .on("mouseover", function (d) {
                    tooltip_div.transition()
                        .duration(200)
                        .style("opacity", .9);
                    tooltip_div.html(
                        genome1 + ": " + d.entry_1.omaid + "<br/>" +
                        genome2 + ": " + d.entry_2.omaid + "<br/>" +
                        "g1 name  : " + d.entry_1.canonicalid + "<br/>" +
                        "g2 name  : " + d.entry_2.canonicalid + "<br/>" +
                        metric_option.short_name + ": " + d[metric_option.accessor].toPrecision(3)
                    )
                        .style("left", (d3.event.pageX) + "px")
                        .style("top", (d3.event.pageY - 50) + "px");
                })
                .on("mouseout", function (d) {
                    tooltip_div.transition()
                        .duration(500)
                        .style("opacity", 0);
                });

            // svg x axis
            var gX = svg_dotplot.append("g")
                .attr("class", "axis axis--x")
                .attr("transform", "translate(0," + (height) + ")")
                .call(xAxis)
                .append("text")
                .attr("class", "label")
                .attr("x", width)
                .attr("fill", "#000")
                .attr("y", -6)
                .style("text-anchor", "end")
                .text(function () {
                    return genome1 + "." + chromosome1
                });

            // svg y axis
            var gY = svg_dotplot.append("g")
                .attr("class", "axis axis--y")
                .attr("transform", "translate(0,0)")
                .call(yAxis).append("text")
                .attr("class", "label")
                .attr("transform", "rotate(-90)")
                .attr("y", 6)
                .attr("dy", ".71em")
                .attr("fill", "#000")
                .style("text-anchor", "end")
                .text(function () {
                    return genome2 + "." + chromosome2
                });

            svg_dotplot.selectAll(".domain")
                .style("display", "none");

            dotplot.add_legend_color();

            // create zoom d3 object
            var zoom = d3.zoom()
                .scaleExtent([1, 100])
                .translateExtent([[0, 0], [size_plot.width, size_plot.height]])
                .on("zoom", zoomed);

            // attach zoom to brush element
            gbrush_plot.call(zoom).on("dblclick.zoom", null);

            // define variable for d3 zoom state
            var currentZoom = null;

            // function called when zoomed
            function zoomed() {

                // update zoom var
                currentZoom = d3.event.transform;

                // update circles position and size
                gcircles.attr("transform", currentZoom);
                gcircles.style('r', 2.5 /  currentZoom.k);

                // update axis
                svg_dotplot.select(".axis--x").call(xAxis.scale(currentZoom.rescaleX(x)));
                svg_dotplot.select(".axis--y").call(yAxis.scale(currentZoom.rescaleY(y)));

            }


            function brushended_plot() {
                var s = d3.event.selection;

                if (!s) {
                    if (!idleTimeout) return idleTimeout = setTimeout(idled, idleDelay);

                    svg_dotplot.selectAll('circle').classed("active", function () {
                        return 1 === 2
                    });
                    selected_pairs = [];

                    $('#container_table_selection').hide();

                } else {
                    if (brush_action === 'select') {

                        selected_pairs = [];

                        select_brush(s);

                        svg_dotplot.select(".brush").call(brush_plot.move, null);

                        if (selected_pairs.length > 0){

                        $('#table_selection').bootstrapTable('removeAll');

                        $('#table_selection').bootstrapTable('load', selected_pairs);

                        $('#container_table_selection').show()

                            }

                            else{$('#container_table_selection').hide();}

                    }
                    if (brush_action === 'zoom') {

                        // vestige of box selection

                        //zoom_brush_plot(s);

                        svg_dotplot.select(".brush").call(brush_plot.move, null);
                    }
                }
            }

            function idled() {
                idleTimeout = null;
            }

            function zoom_brush_plot(s) {

                /*  VESTIGE OF BOX ZOOMING


                // version test 1

                // take the default scales
                    var scx = x;
                    var scy = y;

                    // update scale if zoomed
                    if (!!currentZoom) {

                        scx = currentZoom.rescaleX(x);
                        scy = currentZoom.rescaleY(y);

                    }

                x.domain([s[0][0], s[1][0]].map(scx.invert, scx));
                y.domain([s[1][1], s[0][1]].map(scy.invert, scy));


                var t = svg_dotplot.transition().duration(750);

                svg_dotplot.select(".axis--x").transition(t).call(xAxis);
                svg_dotplot.select(".axis--y").transition(t).call(yAxis);

                    svg_dotplot.selectAll("circle").transition(t)
                   .attr("cx", function (d) {
                        return x(d.entry_1.locus[0]);
                    })
                    .attr("cy", function (d) {
                        return y(d.entry_2.locus[0]);
                    });


               // version test 2

                var current_scale;
                var current_translatex;
                var current_translatey;

                if (!!currentZoom) {
                        current_scale = currentZoom.k;
                        current_translatex = currentZoom.x;
                        current_translatey = currentZoom.y;
                    }
                    else{current_scale = 1;
                current_translatex = 0;
                current_translatey = 0;}

                console.log(current_scale,current_translatex, current_translatey );


                var bounds = s,
                    dx = bounds[1][0] - bounds[0][0],
                    dy = bounds[1][1] - bounds[0][1],
                    xb = (bounds[0][0] + bounds[1][0]) / 2,
                    yb = (bounds[0][1] + bounds[1][1]) / 2,
                    scale = Math.max(1, Math.min(100,  0.9/ Math.max(dx / width, dy / height)));

                    var translate = [width / 2 - scale * xb, height / 2 - scale * yb];


                    console.log(scale,translate);

                gbrush_plot
                    .call( zoom.transform, d3.zoomIdentity.translate(translate[0],translate[1]).scale(scale) );

                */

            }

            function select_brush(s) {


                if (s === null) {
                    //handle.attr("display", "none");
                    circle.classed("active", false);
                } else {

                    // selection rectangle
                    var rect = gbrush_plot.select("rect.selection");

                    // Intersect rectangle with nodes
                    var lx = parseInt(rect.attr("x"));
                    var ly = parseInt(rect.attr("y"));
                    var lw = parseInt(rect.attr("width"));
                    var lh = parseInt(rect.attr("height"));

                    // get all 4 coordinates
                    var bxmin = lx;
                    var bxmax = lx + lw;
                    var bymin =  ly + lh ;
                    var bymax =  ly   ;

                    // take the default scales
                    var scx = x;
                    var scy = y;

                    // update scale if zoomed
                    if (!!currentZoom) {

                        scx = currentZoom.rescaleX(x);
                        scy = currentZoom.rescaleY(y);

                    }

                    // get the position coordinates (reverse from scale)
                    bxmin = scx.invert(bxmin);
                    bxmax = scx.invert(bxmax);
                    bymin = scy.invert(bymin);
                    bymax = scy.invert(bymax);

                    var circle = svg_dotplot.selectAll('circle');

                    circle.classed("active", function (d) {
                        if (dotplot.between(d.entry_1.locus[0], bxmin, bxmax)) {
                            if (dotplot.between(d.entry_2.locus[0], bymin, bymax)) {
                                if (d3.select(this).attr('visibility') === 'visible') {
                                    selected_pairs.push(d);
                                    return true;
                                }

                            }
                        }
                        return false;
                    });

                    circle.classed("picked", false);
                    picked_datapoint = null;

                }

            }


            // // // // // // // //
            // metric histogram  //
            // // // // // // // // 

            var height_hist = 50;

            var brush_hist = d3.brushX()
                .extent([[0, 0], [width, height_hist]])
                .on("brush end", brushed_hist);

            var x_hist = d3.scaleLinear().range([0, width]),
                y_hist = d3.scaleLinear().range([height_hist, 0]);

            var xAxis_hist = d3.axisBottom(x_hist).ticks(10)
                .tickFormat(function (d) {
                    return d3.formatPrefix(".1", 1e1)(d)
                });

            var area = d3.area()
                .curve(d3.curveBasis)
                .x(function (d) {
                    return x_hist(d.value);
                })
                .y0(height_hist)
                .y1(function (d) {
                    return y_hist(d.freq);
                });

            x_hist.domain(d3.extent(hist_color, function (d) {
                return d.value;
            }));
            y_hist.domain([0, d3.max(hist_color, function (d) {
                return d.freq;
            })]);

            var context = svg_hist.append("g")
                .attr("class", "context")
                .attr("transform", "translate(" + 0 + "," + 0 + ")");

            context.append("path")
                .datum(hist_color)
                .attr("class", "area")
                .attr("d", area);

            context.append("g")
                .attr("class", "axis axis--x")
                .attr("transform", "translate(0," + height_hist + ")")
                .call(xAxis_hist)
                .append("text")
                .attr("transform", "translate(-10," + 0 + ")")
                .attr("class", "label")
                .attr("x", width)
                .attr("fill", "#000")
                .attr("y", -6)
                .style("text-anchor", "end")
                .text(metric_option.long_name);

            var gBrush = context.append("g");
            gBrush.attr("class", "brush")
                .call(brush_hist);

            // style brush resize handle
            // https://github.com/crossfilter/crossfilter/blob/gh-pages/index.html#L466
            var brushResizePath = function (d) {
                var e = +(d.type === "e"),
                    x = e ? 1 : -1,
                    y = height_hist / 2;
                return "M" + (.5 * x) + "," + y + "A6,6 0 0 " + e + " " + (6.5 * x) + "," + (y + 6) + "V" + (2 * y - 6) + "A6,6 0 0 " + e + " " + (.5 * x) + "," + (2 * y) + "Z" + "M" + (2.5 * x) + "," + (y + 8) + "V" + (2 * y - 8) + "M" + (4.5 * x) + "," + (y + 8) + "V" + (2 * y - 8);
            };

            var handle = gBrush.selectAll(".handle--custom")
                .data([{type: "w"}, {type: "e"}])
                .enter().append("path")
                .attr("class", "handle--custom")
                .attr("stroke", "#000")
                .attr("cursor", "ew-resize")
                .attr("d", brushResizePath);

            gBrush.call(brush_hist.move, x_hist.range());

            context.selectAll('g.tick')
                .select('text') //grab the tick line
                .attr('font-weight', "bold");

            //gBrush.select('rect.selection').attr("transform", function (d, i) {
            //            return "translate(0 ," + -50 + ")";
            //        });

            function brushed_hist() {

                if (d3.event.sourceEvent && d3.event.sourceEvent.type === "zoom") return; // ignore brush-by-zoom
                var s = d3.event.selection;

                if (s === null) {
                    s = x_hist.range();
                    handle.attr("display", "none");

                } else {

                    filter_max_distance = x_hist.invert(s[1]);
                    filter_min_distance = x_hist.invert(s[0]);

                    dotplot.update_visibility_dot();
                    handle.attr("display", null).attr("transform", function (d, i) {
                        return "translate(" + s[i] + "," + -height_hist / 4 + ")";
                    });
                }
            }


        });

    }

    return DotPlot;
};
