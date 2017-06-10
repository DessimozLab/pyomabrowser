var dotplot_theme;

dotplot_theme = function () {

    function DotPlot(container_id, url_json, genome1,genome2,chromosome1,chromosome2) {

        // METHODS
        this.create_containers = function (container) {

            // create plot div
            var plot = document.createElement('div');
            plot.id = "plot_div";
            plot.style.width = "100%";
            container.appendChild(plot);

            // create legend div
            var ldiv = document.createElement('div');
            ldiv.id = "plot_legend";
            ldiv.style.width = "100%";
            container.appendChild(ldiv);
        }
        this.add_color_legend = function(color_threshold, svg_legend){

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
        this.set_up_brush_action_setting = function () {
            genedata_picker = d3.select("#action_dropdown").selectAll(".action_dropdown-li").on('click', function () {
                if (this.id === 'ba-export') {
                    brush_action = 'export';
                    console.log(brush_action);
                }
                else  {
                    brush_action = 'zoom';
                    console.log(brush_action);
                }

            });
        }
        this.set_up_filter_setting = function () {
            genedata_picker.attr('min', min_distance);
            genedata_picker.attr('max', max_distance);
            genedata_picker.on('change', function () {

                //filter_max_distance = parseFloat(this.value);
                // dots
                svg_dotplot.selectAll("circle")
                    .attr("visibility", function(d) {
                        return parseFloat(d.distance) < filter_max_distance ? "visible" : "hidden";})
            });

        };
        this.calculate_frequencies = function(arr){

            function sortNumber(a,b) {
                return a - b;
            }
            var a = [], b = [], prev;

            arr.sort(sortNumber);
            for ( var i = 0; i < arr.length; i++ ) {
                if ( arr[i] !== prev ) {
                    a.push(arr[i]);
                    b.push(1);
                } else {
                    b[b.length-1]++;
                }
                prev = arr[i];
            }

            return [a, b];
        }
        this.update_visibility_dot = function(){

            function between(x, min, max) {
                return x >= min && x <= max;
            }

            svg_dotplot.selectAll("circle")
                .attr("visibility", function(d) {

                    var dist = parseInt(d.distance);


                    if (between(dist, filter_min_distance, filter_max_distance)){
                        return "visible";

                    }
                    return "hidden";

                })

        };

        // VARIABLES
        var dotplot = this;

        // container with dotplot div and legend color div
        var cviewer = document.getElementById(container_id), cdotplot, clegend;
        dotplot.create_containers(cviewer);

        var brush_action;
        dotplot.set_up_brush_action_setting();

        var filter_max_distance, filter_min_distance;
        var genedata_picker = d3.select("#min_distance_setting_id");

        // margin to apply on the dotplot svg
        var margin = {top: 50, right: 20, bottom: 20, left: 50}

        // size of the svg
        var size_plot = {
            width: cviewer.offsetWidth,
            height: 300
        };

        var size_legend = {width: size_plot.width, height: 200};

        var width = size_plot.width  - margin.left - margin.right,
            height = size_plot.height - margin.top - margin.bottom;

        var svg_dotplot = d3.select("#plot_div").append("svg")
            .attr("width", size_plot.width)
            .attr("height", size_plot.height)
            .append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        var svg_legend = d3.select("#plot_legend").append("svg")
            .attr("width", size_legend.width)
            .attr("height", size_legend.height)
            .append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        d3.json(url_json, function(error, data) {

            var data_slice_distance = [];

            data.forEach(function(d) {
                data_slice_distance.push(parseInt(d.distance));
            });

            var hist_color_split =  dotplot.calculate_frequencies(data_slice_distance);

            var hist_color = [];

            for ( var i = 0; i < hist_color_split[0].length; i++ ) {
                hist_color.push({'distance':hist_color_split[0][i], 'freq':hist_color_split[1][i]})
            }

            // data boundaries
            min_distance = d3.min(data, function(d) { return parseFloat(d.distance); });
            max_distance = d3.max(data, function(d) { return parseFloat(d.distance); });
            min_position_x = d3.min(data, function(d) { return d.gene1; });
            max_position_x = d3.max(data, function(d) { return d.gene1; });
            min_position_y = d3.min(data, function(d) { return d.gene2; });
            max_position_y = d3.max(data, function(d) { return d.gene2; });

            filter_max_distance = max_distance;

            // color scale
            color_domain = [min_distance, max_distance];
            color_range = ["#6e7c5a", "#760000"];
            color_threshold = d3.scaleLinear().domain(color_domain).range(color_range);


            // scaling of data on axis
            var x0 = [min_position_x, max_position_x],
                y0 = [min_position_y, max_position_y],
                x = d3.scaleLinear().domain(x0).range([0, width]),
                y = d3.scaleLinear().domain(y0).range([height, 0]);

            // x axis
            var xAxis = d3.axisBottom(x)
                .ticks(12)
                .tickFormat(function(d) {return d3.formatPrefix(".1", 1e6)(d) + 'b'})

            // y axis
            var yAxis = d3.axisLeft(y)
                .ticks(12 * height / width)
                .tickFormat(function(d) {return d3.formatPrefix(".1", 1e6)(d) + 'b'});

            // brush object
            var brush = d3.brush().on("end", brushended),
                idleTimeout,
                idleDelay = 350;

            // dots
            svg_dotplot.selectAll("circle")
                .attr("class", "circle")
                .data(data)
                .enter().append("circle")
                .attr("cx", function(d) { return x(d['gene1']); })
                .attr("cy", function(d) { return y(d['gene2']); })
                .attr("r", 2.5)
                //.attr("visibility", function(d) {
                //    return parseFloat(d.distance) <= filter_max_distance ? "visible" : "hidden";})
                .attr("fill", function(d){return color_threshold(d.distance)});

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
                .text(function(){return genome1 +"."+ chromosome1});

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
                .text(function(){return genome2 +"."+ chromosome2});

            svg_dotplot.selectAll(".domain")
                .style("display", "none");

            svg_dotplot.append("g")
                .attr("class", "brush")
                .call(brush);

            dotplot.set_up_filter_setting();

            // Add a legend for the color values.
            var legend = svg_dotplot.selectAll(".legend")
                .data(color_threshold.ticks(10).slice(1).reverse())
                .enter().append("g")
                .attr("class", "legend")
                .attr("visibility", "visible")
                .attr("transform", function(d, i) { return "translate(" + (width - 30) + "," + (20 + i * 10) + ")"; });

            legend.append("rect")
                .attr("width", 10)
                .attr("height", 10)
                .style("fill", color_threshold);

            legend.append("text")
                .attr("x", 15)
                .attr("y", 6)
                .attr("dy", ".35em")
                .style("font-size","8px")
                .style("text-anchor", "start")
                .text(function(d){console.log(d); return d});

            svg_dotplot.append("text")
                .attr("class", "label")
                .attr("x", width - 20)
                .attr("y", 10)
                .attr("dy", ".35em")
                .style("text-anchor", "middle")
                .text("Distance");

            // color legend

            var height2 = 50;

            var brush = d3.brushX()
                .extent([[0, 0], [width, height2]])
                .on("brush end", brushed);

            var x2 = d3.scaleLinear().range([0, width]),
                y2 = d3.scaleLinear().range([height2, 0]);

            var xAxis2 = d3.axisBottom(x2).ticks(10)
                .tickFormat(function(d) {return d3.formatPrefix(".1", 1e1)(d)})

            var area2 = d3.area()
                .curve(d3.curveBasis)
                .x(function(d) { return x2(d.distance); })
                .y0(height2)
                .y1(function(d) { return y2(d.freq); });

            x2.domain(d3.extent(hist_color, function(d) { return d.distance; }));
            y2.domain([0, d3.max(hist_color, function(d) { return d.freq; })]);

            var context = svg_legend.append("g")
                .attr("class", "context")
                .attr("transform", "translate(" + 0 + "," + 0 + ")");

            context.append("path")
                .datum(hist_color)
                .attr("class", "area")
                .attr("d", area2);

            context.append("g")
                .attr("class", "axis axis--x")
                .attr("transform", "translate(0," + height2 + ")")
                .call(xAxis2)
                .append("text")
                .attr("transform", "translate(-10," +  0 + ")")
                .attr("class", "label")
                .attr("x", width)
                .attr("fill", "#000")
                .attr("y", -6)
                .style("text-anchor", "end")
                .text("Phylogenetic distance");

            context.append("g")
                .attr("class", "brush")
                .call(brush)
                .call(brush.move, x.range());

            context.selectAll('g.tick')
                .select('text') //grab the tick line
                .attr('fill', function(d){ return color_threshold(d);})
                .attr('font-weight', "bold");


            function brushed() {
                if (d3.event.sourceEvent && d3.event.sourceEvent.type === "zoom") return; // ignore brush-by-zoom
                var s = d3.event.selection || x2.range();

                filter_max_distance = x2.invert(s[1]);
                filter_min_distance = x2.invert(s[0]);

                dotplot.update_visibility_dot();

                console.log( x2.invert(s[0]), x2.invert(s[1]));
            }


            function brushended() {
                var s = d3.event.selection;
                if (!s) {
                    if (!idleTimeout) return idleTimeout = setTimeout(idled, idleDelay);
                    x.domain(x0);
                    y.domain(y0);
                } else {
                    x.domain([s[0][0], s[1][0]].map(x.invert, x));
                    y.domain([s[1][1], s[0][1]].map(y.invert, y));
                    svg_dotplot.select(".brush").call(brush.move, null);
                }
                if (brush_action === 'export'){
                    console.log(s[0][0], s[1][0])}
                else{
                    zoom_brush();
                }
            }

            function idled() {
                idleTimeout = null;
            }

            function zoom_brush() {
                var t = svg_dotplot.transition().duration(750);
                svg_dotplot.select(".axis--x").transition(t).call(xAxis);
                svg_dotplot.select(".axis--y").transition(t).call(yAxis);
                svg_dotplot.selectAll("circle").transition(t)
                    .attr("cx", function(d) { return x(d['gene1']); })
                    .attr("cy", function(d) { return y(d['gene2']); });
            }

        });

    }

    return DotPlot;
};
