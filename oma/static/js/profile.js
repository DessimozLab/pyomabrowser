(function (exports) {
    "use strict";

    exports.visualize_all = function (class_of_entries, data, value_tax, value_sp, external_profile, attr_name) {


        function zoom(svg, chart) {

            // d3.zoomTransform(svg.node()).k

            const extent = [[margin.left, margin.top], [chart.width - margin.right, chart.height - margin.top]];

            var zoom_d = d3.zoom()
                .scaleExtent([1, 50])
                .translateExtent(extent)
                .extent(extent)
                .on("zoom", function () {

                    var e = d3.event.transform;

                    $.each(array_chart, function (idx, chart_e) {
                        if (d3.event.sourceEvent instanceof MouseEvent || d3.event.sourceEvent instanceof WheelEvent) {
                            chart_e.chart.call(zoom_d.transform, e)
            }

                        zoomed(e, chart_e)
                    });
                });

            svg.call(zoom_d)


            /*


            var button_zoomin = document.getElementById("button_zoomin");
            button_zoomin.onclick = function() {
                d3.select(svg).transition().call(zoom_d.scaleBy, 2)
            };

            var button_zoomout = document.getElementById("button_zoomout");
            button_zoomout.onclick = function() {
                zoom_d.scaleBy(d3.select(svg), 0.5);
            };

            */


            function zoomed(e, chart_e) {

                chart_e.xscale.range([margin.left, chart_e.width - margin.right]
                    .map(d => e.applyX(d)));

                chart_e.chart.selectAll(".bars rect")
                    .attr("x", function (d) {
                        return chart_e.xscale(d)
                    })
                    .attr("width", chart_e.xscale.bandwidth());

                chart_e.chart.selectAll(".x-axis").call(chart_e.xAxis)


            }
        }

        var margin = {top: 20, right: 20, bottom: 20, left: 20};

        if (attr_name === undefined) {
            attr_name = 'id';
        }

        var array_chart;

        if (external_profile === undefined) {
             array_chart = []
        }
        else {

            array_chart = external_profile

        }

        $.each($(class_of_entries), function (each, value) {

            // Retreive the entry ID
            var entry_id = $(this).attr(attr_name);
            var data_item = data[entry_id];
            var container = this;


            var width = container.offsetWidth - margin.left - margin.right,
                height = 120 - margin.top - margin.bottom;

            container.innerHTML ="";

            var chart_data = exports.run_profile_vis(container, data_item, value_tax, value_sp, margin, width, height);

            array_chart.push({
                'chart': chart_data.svg,
                'xscale': chart_data.x,
                'width': width,
                'height': height,
                'xAxis': chart_data.xAxis
            })
        });

        $.each(array_chart, function (idx, chart) {

            chart.chart.call(zoom, chart)

        });

        return array_chart

    };

    exports.run_profile_vis = function (container, data_profile, taxon, species, margin, width, height) {

        if (!data_profile) return;

        var filter_data = []

        $.each(data_profile, function (idx, val) {

            if (val === 1 ) {
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


            if (zoom_level > 10) {
                return _50
            }
            else if (zoom_level > 5) {
                return _200
            }
            else {
                return _root
            }
        }


        var svg = d3.select(container).append("svg")
            .attr("viewBox", [0, 0, width, height])


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

        var color_scale = d3.scaleThreshold()
            .domain(data_taxon(d3.zoomTransform(svg.node()).k).map(function (d) {
                return d.idx
            }))
            .range(d3.schemeCategory10);

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
        svg.node();

        return {'svg': svg, 'x': x, 'xAxis': xAxis};


    };

})(this.profile = {});
