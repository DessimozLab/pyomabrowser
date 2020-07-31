
(function (exports) {
    "use strict";

    exports.visualize_all = function (class_of_entries, data, value_tax, value_sp, attr_name  ) {

        if(attr_name === undefined)
        { attr_name = 'id'; }

        $.each($(class_of_entries), function (each, value) {

            // Retreive the entry ID
            var entry_id = $(this).attr(attr_name);
            var data_item = data[entry_id];
            var container = this;

            exports.run_profile_vis(container, data_item, value_tax, value_sp);
        });
    };

    exports.run_profile_vis = function(container, data_profile, taxon, species) {

            if (!data_profile) return;

            var _root = [];
            var _200 = [];
            var _50 = [];

            $.each( taxon, function( level, ltax ) {

            if (level == 'root'){

                $.each( ltax, function( name, idx ) {
                    _root.push({'idx':idx[0],'taxon':name});
                })
            }

            else if (level == '50'){

                $.each( ltax, function( name, idx ) {
                    _50.push({'idx':idx[0],'taxon':name});
                })
            }

            else if (level == '200'){

                $.each( ltax, function( name, idx ) {
                    _200.push({'idx':idx[0],'taxon':name});
                })
            }

        });

            var sp_array = []
            $.each( species, function( idx, name) {
                sp_array.push({'idx':idx,'name':name});

            })


            var data_taxon = _root;

            var margin = {top: 20, right: 20, bottom: 20, left: 20},

                width = container.offsetWidth - margin.left - margin.right,
            height = 120 - margin.top - margin.bottom;

            const svg =  d3.select(container).append("svg")
            .attr("viewBox", [0, 0, width, height])
            .call(zoom);

            var  x = d3.scaleBand()
            .domain(data_profile.map(function(d,i) {return i}))
            .range([margin.left, width - margin.right])
            .padding(0.1)

            var y = d3.scaleLinear()
            .domain([0, d3.max(data_profile, d => d)]).nice()
            .range([height - margin.bottom, margin.top])

            var xAxis = g => g
            .attr("transform", `translate(0,${height - margin.bottom})`)
            .call(d3.axisBottom(x)
                .tickValues(data_taxon.map(function(d) {return d.idx}))
            .tickFormat(function (d) {
                var result = data_taxon.find(obj => {return obj.idx === d});
                return result.taxon;
            }));


            var yAxis = g => g
            .attr("transform", `translate(${margin.left},0)`)
            .call(d3.axisLeft(y))
            .call(g => g.select(".domain").remove())

            var color_scale = d3.scaleThreshold()
                .domain(data_taxon.map(function(d) {return d.idx}))
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
            .data(data_profile)
            .join("rect")
            .attr("x", function(d,i) { return x(i) })
            .attr("y", d => y(d))
                .attr("fill", function(d, i) {return color_scale(i)})
            .attr("height", d => y(0) - y(d))
            .attr("width", x.bandwidth())
            .on('mouseover',

                function(d,i) {

                div.transition().duration(200).style('opacity', 0.9);
                div.html(sp_array.find(obj => {return obj.idx === i}).name)
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

            function zoom(svg) {



  const extent = [[margin.left, margin.top], [width - margin.right, height - margin.top]];

  svg.call(d3.zoom()
      .scaleExtent([1, 50])
      .translateExtent(extent)
      .extent(extent)
      .on("zoom", zoomed));


  function zoomed() {


    x.range([margin.left, width - margin.right].map(d => d3.event.transform.applyX(d)));
    svg.selectAll(".bars rect").attr("x", function(d,i) { return x(i) }).attr("width", x.bandwidth());

    if (d3.event.transform.k > 10){

        data_taxon = _50

    }

    else if (d3.event.transform.k > 5){

        data_taxon = _200

    }
    else {
        data_taxon = _root
    }

    svg.selectAll(".x-axis").call(xAxis)

    ;
  }
}

    };

})(this.profile={});
