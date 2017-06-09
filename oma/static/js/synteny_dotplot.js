// Based on http://bl.ocks.org/weiglemc/6185069

/*
 genome1/chr1/gene1 are the X data
 genome2/chr2/gene2 are the Y data
 */

var margin = {top: 20, right: 0, bottom: 30, left: 100},
    width = 960 - margin.left - margin.right,
    height = 500 - margin.top - margin.bottom;

/*
 * value accessor - returns the value to encode for a given data object.
 * scale - maps value to a visual display encoding, such as a pixel position.
 * map function - maps from data value to display value
 * axis - sets up axis
 */


// setup x
var xValue = function(d) { return d.gene1;}, // data -> value
    xScale = d3.scale.linear().range([0, width]), // value -> display
    xMap = function(d) { return xScale(xValue(d));}, // data -> display
    xAxis = d3.svg.axis().scale(xScale).orient("bottom");

// setup y
var yValue = function(d) { return d["gene2"];}, // data -> value
    yScale = d3.scale.linear().range([height, 0]), // value -> display
    yMap = function(d) { return yScale(yValue(d));}, // data -> display
    yAxis = d3.svg.axis().scale(yScale).orient("left");



// add the graph canvas to the body of the webpage
var svg = d3.select("#dotplot_container").append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

// add the tooltip area to the webpage
var tooltip = d3.select("dotplot_container").append("div")
    .attr("class", "tooltip")
    .style("opacity", 0);

// load data

//var url = "/oma/syntenyDP/" + genome1 +"/" + genome2 +"/" + chromosome1.replace(/\s/g,"%20") + "/" + chromosome2.replace(/\s/g,"%20") + "/json/" ;

d3.json("/All/dotplot_example.json", function(error, data) {


    var min_distance = d3.min(data, function(d) { return d.score; });
    var max_distance = d3.max(data, function(d) { return d.score; });


    var color = d3.scale.linear().range([min_distance,max_distance]);
    color.domain([d3.rgb("#007AFF"), d3.rgb('#FFF500')]);

    var color = d3.scale.linear().domain([min_distance,max_distance])
      //.interpolate(d3.interpolateHcl)
      .range([d3.rgb("#007AFF"), d3.rgb('#FFF500')]);



    //d3.json(url, function(error, data) {

    // change string (from JSON) into number format
    data.forEach(function(d) {
        d.gene2 = +d.gene2;
        d["gene1"] = +d["gene1"];
    });

    // don't want dots overlapping axis, so add in buffer to data domain
    xScale.domain([d3.min(data, xValue)-1, d3.max(data, xValue)+1]);
    yScale.domain([d3.min(data, yValue)-1, d3.max(data, yValue)+1]);

    // x-axis
    svg.append("g")
        .attr("class", "x axis")
        .attr("transform", "translate(0," + height + ")")
        .call(
            xAxis.ticks(20)
                .tickFormat(function(d) { return d3.format("s")(d) + 'b';}))
        .append("text")
        .attr("class", "label")
        .attr("x", width)
        .attr("y", -6)
        .style("text-anchor", "end")
        .text(function(){return genome1 +"."+ chromosome1});

    // y-axis
    svg.append("g")
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
    svg.selectAll(".dot")
        .data(data)
        .enter().append("circle")
        .attr("class", "dot")
        .attr("r", 3.5)
        .style("fill", function(d) { return color(d.score);})
        .attr("cx", xMap)
        .attr("cy", yMap);

    // draw legend
    var legend = svg.selectAll(".legend")
        .data(color.domain())
        .enter().append("g")
        .attr("class", "legend")
        .attr("transform", function(d, i) { return "translate(0," + i * 20 + ")"; });

    // draw legend colored rectangles
    legend.append("rect")
        .attr("x", width - 18)
        .attr("width", 18)
        .attr("height", 18)
        .style("fill", color);

    // draw legend text
    legend.append("text")
        .attr("x", width - 24)
        .attr("y", 9)
        .attr("dy", ".35em")
        .style("text-anchor", "end")
        .text(function(d) { return d;})
});

