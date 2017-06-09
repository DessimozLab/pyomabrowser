var dotplot_theme;

dotplot_theme = function () {

    function DotPlot(container_id, url_json, genome1,genome2,chromosome1,chromosome2) {

        // METHODS UI
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
        this.add_color_legend = function (color_threshold, svg_legend){

            var formatNumber = d3.format(".0f");

            var x_legend = d3.scale.linear()
                .domain(color_threshold.domain())
                .range([0, 120]);

            var xAxis_legend = d3.svg.axis().scale(x_legend).orient("bottom")
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

        // big container with everything
        var cviewer = document.getElementById(container_id), cdotplot, clegend;
        this.create_containers(cviewer);

        var margin = {top: 20, right: 50, bottom: 30, left: 50}
        var size_plot = {
            width: cviewer.offsetWidth - margin.left - margin.right,
            height: 500 - margin.top - margin.bottom
        };
        var size_legend = {width: size_plot.width, height: 50};

        // setup x
        var xValue = function (d) {
                return d.gene1;
            }, // data -> value
            xScale = d3.scale.linear().range([0, size_plot.width]), // value -> display
            xMap = function (d) {
                return xScale(xValue(d));
            }, // data -> display
            xAxis = d3.svg.axis().scale(xScale).orient("bottom");

        // setup y
        var yValue = function (d) {
                return d["gene2"];
            }, // data -> value
            yScale = d3.scale.linear().range([size_plot.height, 0]), // value -> display
            yMap = function (d) {
                return yScale(yValue(d));
            }, // data -> display
            yAxis = d3.svg.axis().scale(yScale).orient("left");

        var min_distance, max_distance;

        var color_domain, color_range, color_threshold;

        var svg_dotplot = d3.select("#plot_div").append("svg")
            .attr("width", size_plot.width + margin.left + margin.right)
            .attr("height", size_plot.height + margin.top + margin.bottom)
            .append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        var svg_legend = d3.select("#plot_legend").append("svg")
            .attr("width", size_legend.width + margin.left + margin.right)
            .attr("height", size_legend.height + margin.top + margin.bottom)
            .append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

         // Let'start the dot plot with data

        d3.json(url_json, function(error, data) {

            // change string (from JSON) into number format
            data.forEach(function(d) {
                d.gene2 = +d.gene2;
                d["gene1"] = +d["gene1"];
            });

            min_distance = d3.min(data, function(d) { return d.score; });
            max_distance = d3.max(data, function(d) { return d.score; });

            color_domain = [min_distance, max_distance/3, max_distance*2/3,  max_distance];
            color_range = ["#6e7c5a", "#a0b28f", "#d8b8b3", "#b45554", "#760000"]
            color_threshold = d3.scale.threshold().domain(color_domain).range(color_range);

            // PLOT

            // don't want dots overlapping axis, so add in buffer to data domain
            xScale.domain([d3.min(data, xValue)-1, d3.max(data, xValue)+1]);
            yScale.domain([d3.min(data, yValue)-1, d3.max(data, yValue)+1]);

            // x-axis
            svg_dotplot.append("g")
                .attr("class", "x axis")
                .attr("transform", "translate(0," + size_plot.height + ")")
                .call(
                    xAxis.ticks(20)
                        .tickFormat(function(d) { return d3.format("s")(d) + 'b';}))
                .append("text")
                .attr("class", "label")
                .attr("x", size_plot.width)
                .attr("y", -6)
                .style("text-anchor", "end")
                .text(function(){return genome1 +"."+ chromosome1});

            // y-axis
            svg_dotplot.append("g")
                .attr("class", "y axis")
                .call(yAxis.ticks(20)
                    .tickFormat(function(d) { return d3.format("s")(d) + 'b';}))
                .append("text")
                .attr("class", "label")
                .attr("transform", "rotate(-90)")
                .attr("y", 6)
                .attr("dy", ".71em")
                .style("text-anchor", "end")
                .text(function(){return genome2 +"."+ chromosome2});

            // draw dots
            svg_dotplot.selectAll(".dot")
                .data(data)
                .enter().append("circle")
                .attr("class", "dot")
                .attr("r", 2.5)
                .style("fill", function(d) { return color_threshold(d.score);})
                .style('opacity', 0.3)
                .attr("cx", xMap)
                .attr("cy", yMap);

            // LEGEND
            dotplot.add_color_legend(color_threshold, svg_legend);

        });


    }

    return DotPlot;
};
