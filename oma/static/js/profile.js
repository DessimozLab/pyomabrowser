
(function (exports) {
    "use strict";

    exports.visualize_all = function (class_of_entries, data, attr_name ) {

        if(attr_name === undefined)
        { attr_name = 'id'; }


        $.each($(class_of_entries), function (each, value) {
            // Retreive the entry ID
            var entry_id = $(this).attr(attr_name);
            var data_item = data[entry_id];

            var container = this;

            exports.run_profile_vis(container, data_item);
        });
    };

    exports.run_profile_vis = function(container, data_profile) {

            if (!data_profile) return;

            //var data_profile = data_profile.slice(1500,2000);

            // todo filter bar with no height

            var margin = {top: 20, right: 20, bottom: 20, left: 20},
            width = 840 - margin.left - margin.right,
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
            .call(d3.axisBottom(x).tickValues([]))

            var yAxis = g => g
            .attr("transform", `translate(${margin.left},0)`)
            .call(d3.axisLeft(y))
            .call(g => g.select(".domain").remove())


            svg.append("g")
            .attr("class", "bars")
            .attr("fill", "steelblue")
            .selectAll("rect")
            .data(data_profile)
            .join("rect")
            .attr("x", function(d,i) { return x(i) })
            .attr("y", d => y(d))
          .attr("height", d => y(0) - y(d))
          .attr("width", x.bandwidth());



            svg.append("g")
            .attr("class", "x-axis")
            .call(xAxis);


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
    svg.selectAll(".x-axis").call(xAxis);
  }
}





    };




})(this.profile={});
