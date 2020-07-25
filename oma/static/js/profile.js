
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

            var data_profile = data_profile.slice(1500,2000);

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
            .call(d3.axisBottom(x))

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
            .attr("y", d => "0px")
            .attr("height", d => height*d)
            .attr("width", "2px");



            svg.append("g")
            .attr("class", "x-axis")
            .call(xAxis);

            svg.append("g")
            .attr("class", "y-axis")
            .call(yAxis);

            svg.node();


            function zoom(svg) {
  const extent = [[margin.left, margin.top], [width - margin.right, height - margin.top]];

  svg.call(d3.zoom()
      .scaleExtent([1, 8])
      .translateExtent(extent)
      .extent(extent)
      .on("zoom", zoomed));

  function zoomed() {
    x.range([margin.left, width - margin.right].map(d => d3.event.transform.applyX(d)));
    svg.selectAll(".bars rect").attr("x", function(d,i) { return x(i) }).attr("width", "2px");
    svg.selectAll(".x-axis").call(xAxis);
  }
}





            /*

            // set the dimensions and margins of the graph
            var margin = {top: 20, right: 20, bottom: 20, left: 20},
            width = 840 - margin.left - margin.right,
            height = 120 - margin.top - margin.bottom;

            var pad = width /data_profile.length;

            // append the svg object to the body of the page
            var svg = d3.select(container)
              .append("svg")
                .attr("width", width + margin.left + margin.right)
                .attr("height", height + margin.top + margin.bottom)
                .call(zoom)
              .append("g")
                .attr("transform",
                      "translate(" + margin.left + "," + margin.top + ")");

            // X axis
            var xAxis = d3.scaleBand()
              .domain(d3.range(data_profile.length))
                .range([0, pad * data_profile.length])
            .padding(0.2)

            svg.append("g")
                .attr("class", "x-axis")
              .attr("transform", "translate(0," + height + ")")
              .call(d3.axisBottom(xAxis).tickSizeOuter(0))




            // append the rectangles for the bar chart
            svg.selectAll(".bar")
            .data(data_profile)
            .filter(function(d) { return d === "1" })
            .enter().append("rect")
            .attr("class", "bar")
            .attr("x", function(d,i) { return pad*i })
            .attr("y", "0px")
            .attr("width", "2px")
            .attr("height", function(d) { return d*height   })
            .style("fill", function(d) { return d === "1" ? "orange" : "gray"; })


        function zoom(svg) {
  const extent = [[margin.left, margin.top], [width - margin.right, height - margin.top]];

  svg.call(d3.zoom()
      .scaleExtent([1, 8])
      .translateExtent(extent)
      .extent(extent)
      .on("zoom", zoomed));

  function zoomed() {
    xAxis.range([margin.left, width - margin.right].map(d => d3.event.transform.applyX(d)));
    svg.selectAll(".bars rect").attr("x", d => x(d.name)).attr("width", x.bandwidth());
    svg.selectAll(".x-axis").call(xAxis);
  }
}
   */
    };




})(this.profile={});
