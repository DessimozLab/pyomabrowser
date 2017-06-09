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

        // VARIABLES
        var dotplot = this;

        // container with dotplot div and legend color div
        var cviewer = document.getElementById(container_id), cdotplot, clegend;
        this.create_containers(cviewer);

        // margin to apply on the dotplot svg
        var margin = {top: 50, right: 20, bottom: 20, left: 50}

        // size of the svg
        var size_plot = {
            width: cviewer.offsetWidth,
            height: 550
        };

        var size_legend = {width: size_plot.width, height: 50};

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


            // data boundaries
            min_distance = d3.min(data, function(d) { return d.score; });
            max_distance = d3.max(data, function(d) { return d.score; });
            min_position_x = d3.min(data, function(d) { return d.gene1; });
            max_position_x = d3.max(data, function(d) { return d.gene1; });
            min_position_y = d3.min(data, function(d) { return d.gene2; });
            max_position_y = d3.max(data, function(d) { return d.gene2; });

            function linspace(start, end, n) {
        var out = [];
        var delta = (end - start) / (n - 1);

        var i = 0;
        while(i < (n - 1)) {
            out.push(start + (i * delta));
            i++;
        }

        out.push(end);
        return out;
    }

            // color scale
            color_domain = [0, 10];
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
                zoom_brush();
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
