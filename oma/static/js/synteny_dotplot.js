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


        // VARIABLES
        var dotplot = this;

         // big container with dotplot and legend color
        var cviewer = document.getElementById(container_id), cdotplot, clegend;
        this.create_containers(cviewer);

        var margin = {top: 20, right: 50, bottom: 30, left: 50}

        var size_plot = {
            width: cviewer.offsetWidth - margin.left - margin.right,
            height: 500 - margin.top - margin.bottom
        };

        d3.json(url_json, function(error, data) {

            min_distance = d3.min(data, function(d) { return d.score; });
            max_distance = d3.max(data, function(d) { return d.score; });

            min_position_x = d3.min(data, function(d) { return d.gene1; });
            max_position_x = d3.max(data, function(d) { return d.gene1; });

            min_position_y = d3.min(data, function(d) { return d.gene2; });
            max_position_y = d3.max(data, function(d) { return d.gene2; });

            var svg_dotplot = d3.select("#plot_div").append("svg")
            .attr("width", size_plot.width + margin.left + margin.right)
            .attr("height", size_plot.height + margin.top + margin.bottom)
            .append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

            var width = size_plot.width + margin.left + margin.right, height = size_plot.height + margin.top + margin.bottom;

            var k = height / width,
                x0 = [min_position_x, max_position_x],
                y0 = [min_position_y, max_position_y],
                x = d3.scaleLinear().domain(x0).range([0, width]),
                y = d3.scaleLinear().domain(y0).range([height, 0]);
            var xAxis = d3.axisTop(x)
                    .ticks(12)
                    .tickFormat(function(d) {return d3.formatPrefix(".1", 1e6)(d) + 'b'}),
                yAxis = d3.axisRight(y)
                    .ticks(12 * height / width)
                    .tickFormat(function(d) {return d3.formatPrefix(".1", 1e6)(d) + 'b'});

            var brush = d3.brush().on("end", brushended),
                idleTimeout,
                idleDelay = 350;

            svg_dotplot.selectAll("circle")
                .attr("class", "circle")
                .data(data)
                .enter().append("circle")
                .attr("cx", function(d) { return x(d['gene1']); })
                .attr("cy", function(d) { return y(d['gene2']); })
                .attr("r", 2.5);

            svg_dotplot.append("g")
                .attr("class", "axis axis--x")
                .attr("transform", "translate(0," + (height - 10) + ")")
                .call(xAxis);

            svg_dotplot.append("g")
                .attr("class", "axis axis--y")
                .attr("transform", "translate(10,0)")
                .call(yAxis);

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
                zoom();
            }

            function idled() {
                idleTimeout = null;
            }

            function zoom() {
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
