var dotplot_theme;

dotplot_theme = function () {

    function DotPlot(container_id, url_json, genome1, genome2, chromosome1, chromosome2) {

        /////////////
        // METHODS //
        /////////////

        this.between = function (x, min, max) {
            return x >= min && x <= max;
        }
        this.sortNumber = function(a, b) {
            return a - b;
        }

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


        }
        this.set_up_brush_action_setting = function () {

            genedata_picker = d3.select("#action_dropdown").selectAll(".action_dropdown-li").on('click', function () {
                if (this.id === 'ba-select') {
                    brush_action = 'select';
                    d3.select('#brush_ok_zoom').classed('hidden', true)
                    d3.select('#brush_ok_select').classed('hidden', false)
                }
                else {
                    brush_action = 'zoom';
                    d3.select('#brush_ok_zoom').classed('hidden', false)
                    d3.select('#brush_ok_select').classed('hidden', true)
                }

            });
        }

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

        }
        this.update_color_scales = function(){
            color_domain = [filter_min_distance, filter_max_distance];
            color_range = ['#90ee90', '#000080'];
            //color_range = ['#ffbdbd', '#e1f7d5'];
            color_threshold = d3.scaleLinear().domain(color_domain).range(color_range);
        }
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

                })


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
                    if (d[0] == null) d[0] = x_legend.domain()[0];
                    if (d[1] == null) d[1] = x_legend.domain()[1];
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
        }
        this.calculate_frequencies = function (arr) {

            function sortNumber(a, b) {
                return a - b;
            }

            var a = [], b = [], prev;

            arr.sort(sortNumber);
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
        }
        this.compute_histogram_metric = function(data){


            var data_slice_metric = [];

            data.forEach(function (d) {
                data_slice_metric.push(parseInt(d[metric_option.accessor]));
            });

            // make the histogram data
            var val = [], freq = [], prev;

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

            return hist_color

        }

        ///////////////
        // VARIABLES //
        ///////////////

        // This (DotPlot) will be override in the function scope, we keep it somewhere.
        var dotplot = this;

        // container with dotplot div and legend color div
        var cviewer = document.getElementById(container_id), cdotplot, chist_metric;
        //dotplot.create_containers(cviewer);

        // variable for the dotplot brush action
        var brush_action = 'select';
        d3.select('#brush_ok_select').classed('hidden', false)
        dotplot.set_up_brush_action_setting();

        // selection variable
        var filter_max_distance, filter_min_distance;
        var selected_pairs = [];

        // margin to apply on the dotplot svg
        var margin_plot = {top: 20, right: 50, bottom: 20, left: 50};

        // size of the dotplot svg
        var size_plot = {  width: cviewer.offsetWidth, height: 450 };

        var svg_dotplot = d3.select("#plot_div").append("svg")
            .attr("width", size_plot.width)
            .attr("height", size_plot.height)
            .append("g")
            .attr("transform", "translate(" + margin_plot.left + "," + margin_plot.top + ")");

        var size_legend = {width: size_plot.width, height: 80};

        var svg_hist = d3.select("#hist_metric").append("svg")
            .attr("width", size_legend.width)
            .attr("height", size_legend.height)
            .append("g")
            .attr("transform", "translate(" + margin_plot.left + "," + 0 + ")");

        var width = size_plot.width - margin_plot.left - margin_plot.right,
            height = size_plot.height - margin_plot.top - margin_plot.bottom;


        var metric_option = {long_name: 'Phylogenetic Distance', short_name: 'Distance',  accessor: 'distance'};

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
                return d.gene1;
            });
            var max_position_x = d3.max(data, function (d) {
                return d.gene1;
            });
            var min_position_y = d3.min(data, function (d) {
                return d.gene2;
            });
            var max_position_y = d3.max(data, function (d) {
                return d.gene2;
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
                    return d3.formatPrefix(".1", 1e6)(d) + 'b'
                })

            // y axis
            var yAxis = d3.axisLeft(y)
                .ticks(12 * height / width)
                .tickFormat(function (d) {
                    return d3.formatPrefix(".1", 1e6)(d) + 'b'
                });

            // brush object
            var brush_plot = d3.brush().on("end", brushended_plot),
                idleTimeout,
                idleDelay = 350;

            // Define the div for the tooltip
            var tooltip_div = d3.select("body").append("div")
                .attr("class", "tooltip")
                .style("opacity", 0);

            svg_dotplot.append("g")
                .attr("class", "brush")
                .call(brush_plot);

            // dots
            svg_dotplot.selectAll("circle")
                .attr("class", "circle")
                .data(data)
                .enter().append("circle")
                .attr("cx", function (d) {
                    return x(d['gene1']);
                })
                .attr("cy", function (d) {
                    return y(d['gene2']);
                })
                .attr("r", 2.5)
                .attr("fill", function (d) {
                    return color_threshold(d[metric_option.accessor])
                })
                .on("mouseover", function(d) {
                    tooltip_div.transition()
                        .duration(200)
                        .style("opacity", .9);
                    tooltip_div.html(
                        genome1 + ": "+d.gene1 + "<br/>" +
                        genome2 + ": "+d.gene2 + "<br/>" +
                            "g1 name  : "+d.gene1id + "<br/>" +
                            "g2 name  : "+d.gene2id + "<br/>" +
                        metric_option.short_name + ": "+ d[metric_option.accessor]
                    )
                        .style("left", (d3.event.pageX) + "px")
                        .style("top", (d3.event.pageY - 50) + "px");
                })
                .on("mouseout", function(d) {
                    tooltip_div.transition()
                        .duration(500)
                        .style("opacity", 0);
                });

            // svg x axis
            svg_dotplot.append("g")
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
            svg_dotplot.append("g")
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
                })

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
                var e = +(d.type == "e"),
                    x = e ? 1 : -1,
                    y = height_hist / 2;
                return "M" + (.5 * x) + "," + y + "A6,6 0 0 " + e + " " + (6.5 * x) + "," + (y + 6) + "V" + (2 * y - 6) + "A6,6 0 0 " + e + " " + (.5 * x) + "," + (2 * y) + "Z" + "M" + (2.5 * x) + "," + (y + 8) + "V" + (2 * y - 8) + "M" + (4.5 * x) + "," + (y + 8) + "V" + (2 * y - 8);
            }

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

            function brushed_hist() {

                if (d3.event.sourceEvent && d3.event.sourceEvent.type === "zoom") return; // ignore brush-by-zoom
                var s = d3.event.selection;

                if (s == null) {
                    s = x_hist.range();
                    handle.attr("display", "none");
                } else {

                    filter_max_distance = x_hist.invert(s[1]);
                    filter_min_distance = x_hist.invert(s[0]);

                    dotplot.update_visibility_dot();
                    handle.attr("display", null).attr("transform", function (d, i) {
                        return "translate(" + s[i] + "," + - height_hist / 4 + ")";
                    });
                }

            }

            function brushended_plot() {
                var s = d3.event.selection;
                if (!s) {
                    if (!idleTimeout) return idleTimeout = setTimeout(idled, idleDelay);
                    x.domain(x0);
                    y.domain(y0);
                    svg_dotplot.selectAll('circle').classed("active", function () {
                        return 1 === 2
                    });
                    selected_pairs = []
                    $('#container_table_selection').hide();
                    zoom_brush_plot();
                } else {
                    if (brush_action === 'select') {

                        console.log(s[0][0], s[1][0]);
                        console.log(s[0][1], s[1][1]);
                        selected_pairs = [];
                        select_brush(s);
                        svg_dotplot.select(".brush").call(brush_plot.move, null);

                        $('#table_selection').bootstrapTable('removeAll');

                        $('#table_selection').bootstrapTable('load', selected_pairs);

                        $('#container_table_selection').show()


                    }
                    else {
                        x.domain([s[0][0], s[1][0]].map(x.invert, x));
                        y.domain([s[1][1], s[0][1]].map(y.invert, y));
                        svg_dotplot.select(".brush").call(brush_plot.move, null);
                        zoom_brush_plot();
                    }
                }
            }

            function idled() {
                idleTimeout = null;
            }

            function zoom_brush_plot() {
                var t = svg_dotplot.transition().duration(750);
                svg_dotplot.select(".axis--x").transition(t).call(xAxis);
                svg_dotplot.select(".axis--y").transition(t).call(yAxis);
                svg_dotplot.selectAll("circle").transition(t)
                    .attr("cx", function (d) {
                        return x(d['gene1']);
                    })
                    .attr("cy", function (d) {
                        return y(d['gene2']);
                    });
            }

            function select_brush(s) {

                if (s == null) {
                    //handle.attr("display", "none");
                    circle.classed("active", false);
                } else {
                    var bxmin = x.invert(s[0][0]);
                    var bxmax = x.invert(s[1][0]);

                    var bymin = y.invert(s[1][1]);
                    var bymax = y.invert(s[0][1]);

                    var circle = svg_dotplot.selectAll('circle')
                    circle.classed("active", function (d) {
                        if (dotplot.between(d['gene1'], bxmin, bxmax)) {
                            if (dotplot.between(d['gene2'], bymin, bymax)) {
                                if (d3.select(this).attr('visibility') === 'visible') {
                                    selected_pairs.push(d);
                                    return 1 === 1

                                }

                            }
                        }
                        return 1 === 2;
                    });
                }

            }

        });

    }

    return DotPlot;
};
