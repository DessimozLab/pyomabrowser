/************************ LICENCE ***************************
 *     This file is part of <pyomabrowser>
 *     Copyright (C) <2018> SIB Swiss Institute of Bioinformatics
 *
 *     This program is free software: you can redistribute it and/or modify
 *     it under the terms of the GNU Affero General Public License as
 *     published by the Free Software Foundation, either version 3 of the
 *     License, or (at your option) any later version.
 *
 *     This program is distributed in the hope that it will be useful,
 *     but WITHOUT ANY WARRANTY; without even the implied warranty of
 *     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *     GNU Affero General Public License for more details.
 *
 *     You should have received a copy of the GNU Affero General Public License
 *    along with this program.  If not, see <http://www.gnu.org/licenses/>
 *
 *****************************************************************/
/**
 * File  created on 02/05/18 10:38 by partimo
 * Modified by:
 */
function sb() {

    createPermDiv();

    $('#dolRadio').addClass("active").siblings().removeClass('active');

    // dynamic function call based on the selected buttons value

    $('#colourSel > button').click(function() {
        $(this).addClass('active').siblings().removeClass('active');
        var func = $(this).data('value').split("-");

        if(func[1]){
            scaleName = func[1];
        } else {
            scaleName = func[0];
        }
        window.top[func[0]+"Color"]();

        var placeholder = "#colorscale";

        // init and display legend
        if(scaleName == 'avg_nr_proteins'){
            var colorbar = Colorbar()
	        .origin([15,0])
	        .scale(sqrt_color)
	        .orient("horizontal")
            .barlength(sbWidth / 3)
            .thickness(20);
            colorbarObject = d3.select(placeholder).call(colorbar);
            $(placeholder).css('visibility','visible');
        } else {
            $(placeholder).css('visibility','hidden');
        }


    });

    $("#colourGroup :input").change();
    init_sb();
}


var top_margin = 45,
    sbWidth = window.innerWidth - 10,
    //sbHeight = window.innerHeight - top_margin,
    sbHeight = sbWidth * 0.6,
    rootNode = {},
    scaleName = "dol",
    scaleMax = 0,
    //radius = (Math.min(width, height) / 2)
    radius = (Math.min(sbWidth, sbHeight) / 2) - 10
    path = {};

// Breadcrumb dimensions: width, height, spacing, width of tip/tail.
var b = {
  w: 70, h: 20, s: 3, t: 7
};

var x = d3.scale.linear()
    .range([0, 2 * Math.PI]);

var vals = {
    "avg_nr_proteins" : [],
    "nr_genomes" : [],
    "size" : []
}

// more compact sunburst, proportianally sized root ring
//var y = d3.scale.sqrt().range([0, radius]);
// linear sized rings
var y = d3.scale.linear().range([0, radius]);

// size/area of the slice is nr_genomes
var partition = d3.layout.partition()
    .value(function(d) {
        return d.nr_genomes;
    });

var arc = d3.svg.arc()
    .startAngle(function(d) { return Math.max(0, Math.min(2 * Math.PI, x(d.x))); })
    .endAngle(function(d) { return Math.max(0, Math.min(2 * Math.PI, x(d.x + d.dx))); })
    .innerRadius(function(d) { return Math.max(0, y(d.y)); })
    .outerRadius(function(d) { return Math.max(0, y(d.y + d.dy)); });


var svg = d3.select("#chart")
    .on("touchstart", nozoom)
    .on("touchmove", nozoom)
    .append("svg")
    .attr("id", "sbSvg")
    .attr("width", sbWidth)
    .attr("height", sbHeight)
    .call(d3.behavior.zoom().on("zoom", function () {
    svg.attr("transform", "translate(" + d3.event.translate + ")" + " scale(" + d3.event.scale + ")")
    }))
    .append("g")
    .attr("id", "container")
    .attr("transform", "translate(" + sbWidth / 2 + "," + (sbHeight / 2) + ")");

var all_names = [];

$(document).on('keyup', '#search', function(e) {
  if (e.keyCode == 13) {
      findByName();
  }
});

var augment_data = function(node) {

    if(!node.lineage) {
        node.lineage = "";
    }

    if (!node.children) {
        node.nr_genomes = (node.nr_genomes) ? node.nr_genomes : 1;
        node.avg_nr_proteins = node.nr_proteins / node.nr_genomes;
    } else {
        node.children.forEach(function(child) {
            child.lineage = node.lineage+" > "+child.name;
            child = augment_data(child)
            node.nr_genomes = (node.nr_genomes) ? node.nr_genomes + child.nr_genomes : child.nr_genomes;
            node.nr_proteins = (node.nr_proteins) ? node.nr_proteins + child.nr_proteins : child.nr_proteins;
            node.avg_nr_proteins = node.nr_proteins / node.nr_genomes;
        });
    }

    if(node.id){
        all_names.push({label: node.name+" ("+node.id+")", value: node.name});
    } else {
        all_names.push({label: node.name, value: node.name});
    }

    if (node.nr_genomes && vals.nr_genomes < node.nr_genomes){
        vals.nr_genomes = node.nr_genomes;
    }

    if (node.avg_nr_proteins && vals.avg_nr_proteins < node.avg_nr_proteins){
        vals.avg_nr_proteins = +node.avg_nr_proteins;
    }
    return node;
}

var div = d3.select("body").append("div")
    .attr("class", "tooltip")
    .style("opacity", 0);

var divsearchtip = d3.select("body").append("div")
    .attr("class", "searchtip")
    .style("opacity", 0);

var scales = {
        "avg_nr_proteins" : [],
        "dol" : []
    };

function scaleGen() {

    for (var key in vals) {

        var min = 1;
        var max = vals[key];
        //var max = 50000; // limit max val
        var steps = 10;
        var increments = ((max - min) / steps).toFixed(0);
        var arr = [];

        for (var i = 0; i <= steps; ++i) {
            arr.push(min + increments * i);
        }

        arr.push(max);

        scales[key] = arr;
    }

    //console.log(scales);

}

var linear_color = d3.scale.linear();
var log_color = d3.scale.log();
//var sqrt_color = d3.scale.sqrt();
var sqrt_color = d3.scale.pow().exponent(0.7);
var quantile_color = d3.scale.quantile();

function heatmapColor() {

    scaleMax = (d3.max(scales[scaleName])) > 50000 ? 50000 : d3.max(scales[scaleName]);

    linear_color.domain([1, scaleMax]);
    linear_color.range(["#90daac","#2d1994"]);

    log_color.domain([1, scaleMax]);
    log_color.range(["#90daac","#2d1994"]);

    sqrt_color.domain([1, 5000, 20000, scaleMax]);
    sqrt_color.range(["#90daac","#2d1994","#41b6c4", "#e58100"]);
    sqrt_color.tickFormat('.3s');

    quantile_color.domain([1, scaleMax]);
    quantile_color.range(["#90daac","#41b6c4","#2c7fb8","#253494"]);

    d3.selectAll("path").transition().attr("fill", function(d) {
        return sqrt_color(d[scaleName]);
    });
}

function dolColor() {
    d3.selectAll("path").transition().attr("fill", color);
}

function findByName(term){

    if(!term){
        var term = document.getElementById("search").value;
    }

    term = term.toUpperCase();

    d3.selectAll("path").style("stroke-width", "").style("stroke", "").style("opacity", 1);
    divsearchtip.transition().duration(800).style("opacity", 0)

    if(term == "") {
        return false;
    }

    svg.selectAll("path").style("opacity", 0.3);
    var found = false;

    svg.selectAll("path")[0].forEach(function (d) {

        if (d3.select(d).data()[0].name.toUpperCase() == term || (d3.select(d).data()[0].id && d3.select(d).data()[0].id.toUpperCase() == term)) {

            d3.select(d).style("stroke", "red").transition().duration(900).style("opacity", "0").transition().duration(1200).style("opacity", "1").style("stroke-width", "2px");
                //.style("filter", "url(#glow)");//glow

            divsearchtip.html(d.textContent);

            var tipX = (10 + d.getBoundingClientRect().right).toFixed(0);
            var tipY = (-15 + d.getBoundingClientRect().top).toFixed(0);
            divsearchtip.transition()
                .duration(200)
                .style("opacity", .9)
                .style("left", tipX + "px")
                .style("top", tipY + "px")

            found = true;
        }
    })

    if(!found){
        divsearchtip.html("<h3>No matches</h3>");
        divsearchtip.transition()
                .duration(200)
                .style("opacity", .9)
                .style("left", ($("svg").width() / 2) - 75 + "px")
                .style("top", "200px")
                .style("width", "150px")
                .style("padding", "8px")
    }

}

function zoomIntoName(term){

    if (!arguments.length) {
        var term = document.getElementById("search").value;
    }

    term = term.toUpperCase();

    svg.selectAll("path")[0].forEach(function (d) {
        d3.select(d).style("opacity", 1); //making all paths to opacity 1
        if (d3.select(d).data()[0].name.toUpperCase() == term || (d3.select(d).data()[0].id && d3.select(d).data()[0].id.toUpperCase() == term)) {
            click(d3.select(d).data()[0]);
        }
    });

}

function resetTo(node) {
    if(!node){
        node = rootNode;
        zoom.scale(1);
        zoom.translate([0, 0]);
    }
    click(node);
}

function click(d) {

    if (d3.event !== null && d3.event.defaultPrevented) return; // zoomed

    // reset line styles, reset searchtip
    d3.selectAll("path").style("stroke-width", "1px").style("stroke", "#fff");
    divsearchtip.transition().duration(800).style("opacity", 0);

    // dup code
    if(d.nr_hogs){
        var hogs = "<br>Ancestral genome size: "+d.nr_hogs.toFixed(0);
    } else {
        var hogs = "";
    }

    if(d.avg_nr_proteins){
        var avg_proteins = "<br>Avg genome size: "+d.avg_nr_proteins.toFixed(0);
    } else {
        var avg_proteins = "";
    }

    if(d.id){
        var id = "Species: <a href='https://omabrowser.org/cgi-bin/gateway.pl?f=DisplayOS&p1="+d.id+"'>"+d.id+"</a>";
    } else {
        var id = "";
    }

    var lineageItems = d.lineage.split(" > ");
    lineageItems.shift();
    var lineage = "";
    if(lineageItems.length) {

        lineage = "<p class='lineage'>Lineage: ";

        lineageItems.forEach(function (elem) {
            lineage += "<span>" + elem + "</span>";
        })

        lineage += "</p>";
    }

    d3.select('#permdiv')
    .html("<h5 style='vertical-align: middle;border-bottom: 1px solid black;padding-bottom: 3px;'>Selected<br>" +
        " <strong>"+d.name+
        "</strong><br><span style='font-size: 1em;margin-left: 5px;'>(Taxonid: "+d.taxid+
        ")</span></h5><p>"+
        id+
        "<br>Genomes: "+d.nr_genomes+
        avg_proteins+
        hogs+"</p>"+
        lineage)
        .style("right", 20 + "px")
        .style("top", "80px")
        .style("opacity", 0.9)
        .style("z-index", 99)
        .attr("class", "selectedpopup");

    if (d.depth > 0) {
        $('#resetBtn').prop('disabled', false);
    } else {
        $('#resetBtn').prop('disabled', true);
    }
    svg.transition()
        .duration(750)
        .tween("scale", function () {
            var xd = d3.interpolate(x.domain(), [d.x, d.x + d.dx]),
                yd = d3.interpolate(y.domain(), [d.y, 1]),
                yr = d3.interpolate(y.range(), [d.y ? 20 : 0, radius]);
            return function (t) {
                x.domain(xd(t));
                y.domain(yd(t)).range(yr(t));
            };
        })
        .selectAll("path")
        .attrTween("d", function (d) {
            return function () {
                return arc(d);
            };
        });
}

d3.select(self.frameElement).style("height", sbHeight + "px");

// Define a function that returns the color
// for a data point. The input parameter
// should be a data point as defined/created
// by the partition layout.
var color = function(d) {

    // This function builds the total
    // color palette incrementally so
    // we don't have to iterate through
    // the entire data structure.

    // We're going to need a color scale.
    // Normally we'll distribute the colors
    // in the scale to child nodes.
    var colors;

    // The root node is special since
    // we have to seed it with our
    // desired palette.
    if (!d.parent) {

        // Create a categorical color
        // scale to use both for the
        // root node's immediate
        // children. We're using the
        // 10-color predefined scale,
        // so set the domain to be
        // [0, ... 9] to ensure that
        // we can predictably generate
        // correct individual colors.

        if(scaleName != "dol"){
            colors = function () {
                return ["#E76818"];
            };
        } else {
            // 3 domains of life
            colors = d3.scale.category10().domain(d3.range(0,3));
        }


        // White for the root node
        // itself.
        d.color = "#fff";

    } else if (d.children) {

        // Since this isn't the root node,
        // we construct the scale from the
        // node's assigned color. Our scale
        // will range from darker than the
        // node's color to brigher than the
        // node's color.
        if(scaleName != "dol"){

            luminosity = [0.3, 0.5];
            initColor = "#E76818";

        } else  {

            luminosity = [0.2, 0.8];
            initColor = d.color;

        }

        var startColor = d3.hcl(initColor)
                            .darker(luminosity[0]),
            endColor   = d3.hcl(initColor)
                            .brighter(luminosity[1]);

        if(scaleName == "dol") {
            // Create the scale
            colors = d3.scale.linear()
                .interpolate(d3.interpolateHcl)
                .range([
                    startColor.toString(),
                    endColor.toString()
                ])
                .domain([0, d.children.length + 1]);
        }

    }

    if (d.children) {

        // Now distribute those colors to
        // the child nodes. We want to do
        // it in sorted order, so we'll
        // have to calculate that. Because
        // JavaScript sorts arrays in place,
        // we use a mapped version.

        if(scaleName == "avg_nr_proteins"){

            //d.children.map(function (child, i) {
            d.children.map(function (child, i) {
                return {value: child.avg_nr_proteins, idx: i};
            }).forEach(function (child, i) {
                d.children[child.idx].color = quantile_color(child.value)
            });

        } else  {

            d.children.map(function (child, i) {
                return {value: child.value, idx: i};
            }).sort(function (a, b) {
                return b.value - a.value
            }).forEach(function (child, i) {
                d.children[child.idx].color = colors(i);
            });
        }

    }

    return d.color;
};

function init_sb() {

    top_margin = 45,
    sbWidth = $("#genome_panel").width() - 10,
    //sbHeight = $("#genome_panel").height() - top_margin,
    sbHeight = sbWidth * 0.6,
    rootNode = {},
    scaleName = "dol",
    scaleMax = 0,
    //radius = (Math.min(width, height) / 2)
    radius = (Math.min(sbWidth, sbHeight) / 2) - 10
    path = {};

    // Breadcrumb dimensions: width, height, spacing, width of tip/tail.
    b = {
      w: 70, h: 20, s: 3, t: 7
    };

    x = d3.scale.linear()
        .range([0, 2 * Math.PI]);

    vals = {
        "avg_nr_proteins" : [],
        "nr_genomes" : [],
        "size" : []
    }

    // more compact sunburst, proportianally sized root ring
    //var y = d3.scale.sqrt().range([0, radius]);
    // linear sized rings
    y = d3.scale.linear().range([0, radius]);

    // size/area of the slice is nr_genomes
    partition = d3.layout.partition()
        .value(function(d) {
            return d.nr_genomes;
        });

    arc = d3.svg.arc()
        .startAngle(function(d) { return Math.max(0, Math.min(2 * Math.PI, x(d.x))); })
        .endAngle(function(d) { return Math.max(0, Math.min(2 * Math.PI, x(d.x + d.dx))); })
        .innerRadius(function(d) { return Math.max(0, y(d.y)); })
        .outerRadius(function(d) { return Math.max(0, y(d.y + d.dy)); });

    zoom = d3.behavior.zoom().on("zoom", zoomed);

    svg = d3.select("#chart")
        .on("touchstart", nozoom)
        .on("touchmove", nozoom)
        .append("svg")
        .attr("id", "sbSvg")
        .attr("width", sbWidth)
        .attr("height", sbHeight)
        .append("g")
        .call(zoom)
        .attr("id", "container")
        .attr("transform", "translate(" + sbWidth / 2 + "," + (sbHeight / 2) + ")")


    var dragListener = d3.behavior.drag()
    .on("drag", function() {
        dragX = d3.event.dx;
        dragY = d3.event.dy;
    });

    svg.call(dragListener);

    var dragging = 0;
    var dragX = 0, dragY = 0;

    dragListener.on("dragstart", function() {
        console.log("drag start");
      dragging = 1;
    });

    dragListener.on("dragend", function() {
        console.log("drag end");
      dragging = 0;
      dragX = 0;
      dragY = 0;
    });

    function zoomed () {
        console.log("raw scale: "+d3.event.scale);
        var scale = d3.event.scale < 4 ? d3.event.scale < 1 ? 1 : d3.event.scale : 4;
        console.log("scale: "+scale);
        var trans = d3.transform(svg.attr("transform"));
        var tpos = trans.translate;
        var tscale = trans.scale;
        var tx = tpos[0];
        var ty = tpos[1];
        var mx = sbWidth/2;
        var my = sbHeight/2;

        var dx =  (mx - tx - dragX)/tscale[0];
        var dy =  (my - ty - dragY)/tscale[1];
        var dx2 = (mx - dx)/scale - dx;
        var dy2 = (my - dy)/scale - dy;

        var tform = "translate(" + dx + "," + dy + ")scale(" + scale + ")translate(" + dx2 + "," + dy2 + ")"
        svg.attr("transform", tform);


    }

    // zoom & drag

    all_names = [];

    //d3.json("genomes.json", function (error, root) {
    //d3.json("http://127.0.0.1:8000/All/genomes.json", function (error, root) {
    d3.json("/All/genomes.json", function (error, root) {
        if (error) throw error;

        root = augment_data(root);
        rootNode = root;

        scaleGen();
        createVisualization(root);
        initializeBreadcrumbTrail();

    });

}

function nozoom() {
  d3.event.preventDefault();
}

function createVisualization(root) {

    svg.append("svg:circle")
      .attr("r", radius)
      .style("opacity", 0);

    svg.selectAll("path")
        .data(partition.nodes(root))
        .enter().append("path")
        .attr("d", arc)
        .style("opacity", 1)
        .attr("fill", color)
        .on("click", click)
        .on("mouseover", mouseover)
        .append("title")
        .text(function (d) {
            return d.name;
        });

        // Add the mouseleave handler to the bounding circle.
        d3.select("#container").on("mouseleave", mouseleave);

}

// Fade all but the current sequence, and show it in the breadcrumb trail.
function mouseover(d) {
    if(d.nr_hogs){
        var hogs = "<br>Ancestral genome size: "+d.nr_hogs.toFixed(0);
    } else {
        var hogs = "";
    }

    if(d.avg_nr_proteins){
        var avg_proteins = "<br>Avg genome size: "+d.avg_nr_proteins.toFixed(0);
    } else {
        var avg_proteins = "";
    }

    d3.select("#explanation").style("visibility", "");

    var sequenceArray = getAncestors(d);
    updateBreadcrumbs(sequenceArray);

    // highlight colorbar
    if ((typeof colorbarObject !== 'undefined') && (d.avg_nr_proteins)){
        colorbarObject.pointTo(d.avg_nr_proteins.toFixed(0));
        if(!$("#colorbarNumber").length){
            $("svg.colorbar").after('<span id="colorbarNumber"></span>');
            $("#colorBarNumber").css('left', $("svg.colorbar").width() + 10);
        }
        $('#colorbarNumber').text(d.avg_nr_proteins.toFixed(0));
    }

    // Fade all the segments.
    d3.selectAll("path").style("opacity", 0.3).style("stroke-width", "1px").style("stroke", "#fff");

    divsearchtip.transition().duration(800).style("opacity", 0);

    // Then highlight only those that are an ancestor of the current segment.
    svg.selectAll("path")
        .filter(function(node) {
            return (sequenceArray.indexOf(node) >= 0);
        })
        .style("opacity", 1);

    var tooltipTop = function(){
        var element = d3.selectAll('.tooltip').node();
        var ttHeight = element.getBoundingClientRect().sbHeight;
        var ttTop = d3.event.pageY;
        var ttBottom = ttTop + ttHeight + ttBottomMargin;
        var overFlow = ttBottom - sbHeight;

        return (overFlow > 0) ? ttTop - (overFlow + ttBottomMargin) : ttTop - ttTopMargin;
    }

    div.html("<h5 style='vertical-align: middle;border-bottom: 1px solid black;padding-bottom: 3px;'>"+d.name+
        "<br><span style='font-size: 1em;margin-left: 5px;'>(Taxonid: "+d.taxid+
        ")</span></h5>"+
        "<p style='text-align: left;'>Genomes: "+d.nr_genomes+
        avg_proteins+
        hogs+
        "<br>Lineage: <span style='font-size: 1em;'>"+d.lineage+"</span></p>");

    var ttTopMargin = 40;
    var ttBottomMargin = 20;

    div.transition()
        .duration(200)
        .style("opacity", .9)
        .style("left", 20 + "px")
        .style("top", tooltipTop() + "px");

}

// Restore everything to full opacity when moving off the visualization.
function mouseleave() {

  // Hide the breadcrumb trail
  d3.select("#trail").style("visibility", "hidden");

  div.transition().duration(500).style("opacity", 0);

  // Deactivate all segments during transition.
  d3.selectAll("path").on("mouseover", null);

  // Transition each segment to full opacity and then reactivate it.
  d3.selectAll("path")
      .transition()
      .duration(1000)
      .style("opacity", 1)
      .each("end", function() {
              d3.select(this).on("mouseover", mouseover);
      });

  svg.selectAll("path").on("mouseover", mouseover);

  d3.select("#explanation")
      .style("visibility", "hidden");
  $('#colorbarNumber').text('');
}

// Given a node in a partition layout, return an array of all of its ancestor
// nodes, highest first, but excluding the root.
function getAncestors(node) {
  var path = [];
  var current = node;
  while (current.parent) {
    path.unshift(current);
    current = current.parent;
  }
  return path;
}

function initializeBreadcrumbTrail() {
  // Add the svg area.
  var trail = d3.select("#sequence").append("svg:svg")
      .attr("width", sbWidth)
      .attr("height", 40)
      .style("fill", "#4B79A1")
      .attr("id", "trail");

}

// Generate a string that describes the points of a breadcrumb polygon.
function breadcrumbPoints(d, i) {
  var points = [];
  points.push("0,0");
  points.push(b.w + ",0");
  points.push(b.w + b.t + "," + (b.h / 2));
  points.push(b.w + "," + b.h);
  points.push("0," + b.h);
  if (i > 0) { // Leftmost breadcrumb; don't include 6th vertex.
    points.push(b.t + "," + (b.h / 2));
  }
  return points.join(" ");
}

// Update the breadcrumb trail to show the current sequence and percentage.
function updateBreadcrumbs(nodeArray) {

  // Data join; key function combines name and depth (= position in sequence).
  var g = d3.select("#trail")
      .selectAll("g")
      .data(nodeArray, function(d) { return d.name + d.depth; });

  // Add breadcrumb and label for entering nodes.
  var entering = g.enter().append("svg:g");

  entering.append("svg:polygon")
      .attr("points", breadcrumbPoints)
      //.style("fill", function(d) { return colors[d.name]; });
      .attr("fill", "#4B79A1")

  entering.append("svg:text")
      .attr("x", (b.w + b.t) / 2)
      .attr("y", b.h / 2)
      .attr("dy", "0.25em")
      .attr("text-anchor", "middle")
      .text(function(d) { return subStr(d.name); });

  // Set position for entering and updating nodes.
  g.attr("transform", function(d, i) {
    return "translate(" + i * (b.w + b.s) + ", 0)";
  });

  // Remove exiting nodes.
  g.exit().remove();

  // Make the breadcrumb trail visible, if it's hidden.
  d3.select("#trail")
      .style("visibility", "");

}

// Given a node in a partition layout, return an array of all of its ancestor
// nodes, highest first, but excluding the root.
function getAncestors(node) {
  var path = [];
  var current = node;
  while (current.parent) {
    path.unshift(current);
    current = current.parent;
  }
  return path;
}

// Generate a string that describes the points of a breadcrumb polygon.
function breadcrumbPoints(d, i) {
  var points = [];
  points.push("0,0");
  points.push(b.w + ",0");
  points.push(b.w + b.t + "," + (b.h / 2));
  points.push(b.w + "," + b.h);
  points.push("0," + b.h);
  if (i > 0) { // Leftmost breadcrumb; don't include 6th vertex.
    points.push(b.t + "," + (b.h / 2));
  }
  return points.join(" ");
}

function subStr(string){

    var length = 12;
    var trimmedString = string.length > length ? string.substring(0, length - 3) + "..." : string.substring(0, length);
    return trimmedString;
}

function createPermDiv(containerElem) {
    if (!arguments.length || !$( containerElem ).length) {
        var containerElem = "#genome_panel";
    }

    $('<div class="tooltip" style="position: absolute; opacity: 0;" id="permdiv"></div>').prependTo(containerElem);

    $( "#permdiv" ).on( "click", "span", function() {
      console.log("clicked: "+ $( this ).text() );
      zoomIntoName($( this ).text())
    });

}


//Container for the gradients
var defs = svg.append("defs");

//Code taken from http://stackoverflow.com/questions/9630008/how-can-i-create-a-glow-around-a-rectangle-with-svg
//Filter for the outside glow
var filter = defs.append("filter")
    .attr("id","glow");

filter.append("feGaussianBlur")
    .attr("class", "blur")
    .attr("color", "red")
    .attr("stdDeviation","2.5")
    .attr("result","coloredBlur");

var feMerge = filter.append("feMerge");
feMerge.append("feMergeNode")
    .attr("in","coloredBlur");
feMerge.append("feMergeNode")
    .attr("in","SourceGraphic");
