// turn on bootstrap function

$('[data-toggle="tooltip"]').tooltip();


///////////////
/// setting_div DOM  ///
///////////////

// get the button and set update genome function
var btree = document.getElementById("btree");
btree.addEventListener("click", function () {
    btree.addEventListener("click", update_genome_viewer(this.id));
});

var blist = document.getElementById("blist");
blist.addEventListener("click", function () {
    blist.addEventListener("click", update_genome_viewer(this.id));
});

var bhist = document.getElementById("bhist");
bhist.addEventListener("click", function () {
    bhist.addEventListener("click", update_genome_viewer(this.id));
});

// get the viewer container, flush at every update
var cviewer = document.getElementById("genome_panel");

//////////////////
///  FUNCTION  ///
//////////////////

// flush and update viewer container based on viewer type
function filterJSON(json, key, values) {
    var result = [];
    for (i = 0; i < json.length; i++) {
        if (values.indexOf(json[i][key]) > -1) {
            result.push(json[i]);
        }
    }
    return result;
}

// flush and update viewer container based on viewer type
function update_genome_viewer(bid) {

    // clean current viewer
    cviewer.innerHTML = '';
    while (cviewer.firstChild) {
        cviewer.removeChild(cviewer.firstChild);
    }

    // build tree view
    if (bid === "btree") {

        var under = document.createElement('div');

        under.innerHTML = '<nav class="navbar navbar-default">\
        <div class="container-fluid">\
            <div class="nav navbar-nav navbar-left" style="margin-left: 6px; text-align: left;">\
                <button type="button" id="resetBtn" class="navbar-btn btn btn-default btn-sm" style="left: 20px;"\
                 onclick="resetTo();">Reset to root</button>\
                <div class="btn-group btn-group-sm" id="colourSel" role="group" aria-label="...">\
                    <button type="button" class="btn btn-primary" id="heatmapRadio" data-value="heatmap-avg_nr_proteins">Avg number of\
                 Proteins</button>\
                    <button type="button" class="btn btn-primary" id="dolRadio" data-value="dol">Domains of life</button>\
                </div>\
            </div>\
            <div class="nav navbar-nav navbar-right" style="margin-right: 6px;">\
                <div class="form-group input-group navbar-btn input-group-sm">\
                    <input type="text" id="search" class="form-control searchField" placeholder="Search...">\
                    <div class="input-group-btn">\
                        <button type="button" class="btn btn-warning"\
                         onclick="$(\'#search\').val(\'\');findByName();">Clear</button>\
                        <button type="button" class="btn btn-primary" onclick="findByName();">Search</button>\
                        <button type="button" class="btn btn-info" onclick="zoomIntoName();">Zoom into</button>\
                    </div>\
                </div>\
            </div>\
        </div>\
</nav>\
<div id="chart">\
    <div style="position: absolute; margin: 0;" id="sequence"></div>\
    <div style="position: absolute; margin: 20px 0 0 0;" id="colorscale">\
        <div id="explanation" style="visibility: hidden;"></div>\
    </div>\
</div>'
        cviewer.appendChild(under);
        // reset is disabled when root is zoomed
        $('#resetBtn').prop('disabled', true);
        /* init sunburst */
        sb();
        $(document).find('#search').autocomplete({
            //source: all_names,
            lookup: all_names,
            delay: 200,
            minLength: 3,
            //select: function( event, ui ) { findByName(ui.item.value); }
            onSelect: function( event ) { findByName(event.value); }
        });

    }

    // build table view
    else if (bid === "blist") {

        // create empty table
        var tbl = document.createElement('table');
        tbl.id = "genomeTable";
        cviewer.appendChild(tbl);

        // feed it !
        init_table('genomeTable');
    }

    // build hist view
    else if (bid === "bhist") {

        // create the main setting div
        var setting_div = document.createElement('div');
        setting_div.className += "settings_hist";

        // create the collapsible div of the setting
        var setting_div_col = document.createElement('div');
        setting_div_col.id = "settings_hist_collapse";
        setting_div_col.className += "collapse in";

        // add the sorting setting
        setting_div_col.innerHTML += '<b>Sort by:</b> ' +
            '<form > <input type="radio" name="sort_ui" value="prots" checked> Size<br>  ' +
            '<input type="radio" name="sort_ui" value="kingdom" > Kingdom<br> ' +
            '<input type="radio" name="sort_ui" value="uniprot_species_code' +
            '" > Name<br> </form>';

        // add the filtering setting
        setting_div_col.innerHTML += '<b>Show:</b>' +
            '<form > <input type="checkbox" name="filter_ui" value="Eukaryota" checked> Eukaryota<br> ' +
            '<input type="checkbox" name="filter_ui" value="Bacteria" checked> Bacteria<br> ' +
            '  <input type="checkbox" name="filter_ui" value="Archaea" checked> Archaea<br>  </form>'

        // add the size setting
        setting_div_col.innerHTML += '<b>View:</b> ' +
            '<form > <input type="radio" name="view_ui" value="light" > Expanded<br>  ' +
            '<input type="radio" name="view_ui" value="compact" checked > Compacted<br> </form>';

        setting_div.appendChild(setting_div_col);
        cviewer.appendChild(setting_div);


        // create plot div
        var plot = document.createElement('div');
        plot.id = "hist_div";
        plot.style.overflow = "scroll";
        plot.style.width = "100%";
        cviewer.appendChild(plot);

        // create settings collapser button
        var bcol = document.createElement('div');
        bcol.innerHTML = '<button type="button" data-toggle="collapse" data-target="#settings_hist_collapse" class="btn btn-default hide_setting">  <span class="glyphicon glyphicon-cog pull-right "  ></span> </button>';
        cviewer.appendChild(bcol);

        // create legend div
        var ldiv = document.createElement('div');
        ldiv.id = "hist_legend";
        ldiv.style.width = "100%";
        cviewer.appendChild(ldiv);

        // bind settings button with histogram update
        var filter_ui_checks = document.getElementsByName("filter_ui");
        for (i = 0; i < filter_ui_checks.length; i++) {
            filter_ui_checks[i].addEventListener("click", function () {
                init_hist("hist_div")
            })
        }

        // bind settings button with histogram update
        var sort_ui_checks = document.getElementsByName("sort_ui");
        for (i = 0; i < sort_ui_checks.length; i++) {
            sort_ui_checks[i].addEventListener("click", function () {
                init_hist("hist_div")
            })
        }

        // bind settings button with histogram update
        var view_ui_checks = document.getElementsByName("view_ui");
        for (i = 0; i < view_ui_checks.length; i++) {
            view_ui_checks[i].addEventListener("click", function () {
                init_hist("hist_div")
            })
        }

        // build it !
        init_hist('hist_div');

        $('.collapse').collapse();
    }

}
// add the boostrap table in the viewer container
function init_table(div_id) {

    var tab = $('#' + div_id);
    tab.bootstrapTable({
        url: json_genome_url,
        reorderableColumns: true,
        pagination: true,
        pageSize: 50,
        showColumns: true,
        search: true,
        showExport: true,
        pageList: [10, 25, 50, 100, "All"],
        mobileResponsive: true,
        checkOnInit: true,
        undefinedText: "",
        idField: 'code',
        showToggle: 'true',

        columns: [{
            field: 'uniprot_species_code',
            title: 'Code',
            sortable: true,
            formatter: function(value){
                return '<a href="/cgi-bin/gateway.pl?f=DisplayOS&p1='+value+'">'+value+"</a>";
            }
        }, {
            field: 'sciname',
            title: 'Scientific Name',
            sortable: true,
            formatter: tablehooks.format_sciname
        }, {
            field: 'common_name',
            title: 'Common Name',
            sortable: true
        }, {
            field: 'prots',
            title: '# of Sequences',
            sortable: true
        }, {
            field: 'ncbi',
            title: 'NCBI TaxonId',
            sortable: true,
            formatter: function(value) {
                return '<a href="https://uniprot.org/taxonomy/'+value +'">' + value + "</a>";
            }
        }, {
            field: 'kingdom',
            title: 'Kingdom',
            sortable: true
        }]
    });

    var icons = tab.bootstrapTable('getOptions').icons;
    $.extend(icons, {export: 'glyphicon-download-alt', columns: 'glyphicon-list'});
    tab.bootstrapTable('refreshOptions', {'icons': icons});
}

// add the histogram in the viewer container
function init_hist(div_id) {

    // gridlines in y axis function
    function make_y_gridlines() {
        return d3.axisLeft(y)
            .ticks(5)
    }

    // add legend under hist
    function add_legend(div_id) {

        // clean the svg
        d3.select("svg").remove();

        var margin = {top: 10, right: 10, bottom: 50, left: 10};
        var width_legend = cviewer.offsetWidth - margin.left - margin.right;

        var svgLegend = d3.select("#" + div_id).append("svg")
            .attr("width", width_legend)
            .attr("height", 30)
            .append("g").attr("class", "container")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        // draw legend
        var legend = svgLegend.selectAll(".legend")
            .data(color_schema)
            .enter().append("g")
            .attr("class", "legend")
            .attr("transform", function (d, i) {
                return "translate(" + i * 100 + ",0 )";
            });

        // draw legend colored rectangles
        legend.append("rect")
            .attr("x", 18)
            .attr("width", 18)
            .attr("height", 18)
            .style("fill", function (d) {
                return d.color
            });

        // draw legend text
        legend.append("text")
            .attr("x", 40)
            .attr("y", 9)
            .attr("dy", ".35em")
            .style("text-anchor", "start")
            .text(function (d) {
                return d.name;
            })

    }

    function find_color(el, kingdom_name ) {
        if (el.kingdom === kingdom_name){
            return el;
        }
    }

    // clean the svg
    d3.select("svg").remove();

    // define the color schema
    color_schema = [
        {name: "Archaea", color: "#428bca"},
        {name: "Bacteria", color: "#5cb85c"},
        {name: "Eukaryota", color: "#d9534f"},
    ];

    add_legend("hist_legend");

    d3.json(json_genome_url, function (error, data) {
        if (error) throw error;


        // filter by kingdom
        var filter_arr = [];
        var filter_ui_checkbox = document.getElementsByName("filter_ui");
        for (i = 0; i < filter_ui_checkbox.length; i++) {
            if (filter_ui_checkbox[i].checked) {
                filter_arr.push(filter_ui_checkbox[i].value)
            }
        }
        data = filterJSON(data, "kingdom", filter_arr);

        //sort by size or kingdom
        var sortBy;
        var sort_ui_checkbox = document.getElementsByName("sort_ui");
        for (i = 0; i < sort_ui_checkbox.length; i++) {
            if (sort_ui_checkbox[i].checked) {
                sortBy = sort_ui_checkbox[i].value
            }
        }
        data.sort(function (x, y) {
            return d3.descending(x[sortBy], y[sortBy]);
        });

        var margin = {top: 10, right: 10, bottom: 90, left: 10};

        // select view mode
        var view_type;
        var view_ui_checkbox = document.getElementsByName("view_ui");
        for (i = 0; i < view_ui_checkbox.length; i++) {
            if (view_ui_checkbox[i].checked) {
                view_type = view_ui_checkbox[i].value
            }
        }

        if (view_type === "compact"){
            var margin = {top: 10, right: 10, bottom: 10, left: 10};
            var width = cviewer.offsetWidth  - 3*margin.left - 3*margin.right;}
        else {
            var margin = {top: 10, right: 10, bottom: 60, left: 10};
            var width = (data.length) * 10 - margin.left - margin.right;
        }

        var height = 500 - margin.top - margin.bottom;

        var xScale = d3.scale.ordinal().rangeBands([0, width], .03)

        var yScale = d3.scale.linear()
            .range([height, 0]);

        var xAxis = d3.svg.axis()
            .scale(xScale)
            .orient("bottom");

        var yAxis = d3.svg.axis()
            .scale(yScale)
            .orient("left");

        // add the tooltip area to the webpage
        var tooltip = d3.select("body").append("div")
            .attr("class", "tooltip")
            .style("opacity", 0);


        var svgContainer = d3.select("#" + div_id).append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom)
            .append("g").attr("class", "container")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        var hovered_bar;


        xScale.domain(data.map(function (d) {
            return d.uniprot_species_code;
        }));
        yScale.domain([0, d3.max(data, function (d) {
            return d.prots;
        })]);


        function make_y_axis() {

            return d3.svg.axis()
                .scale(yScale)
                .orient("left")
                .ticks(10)
        }

        if (view_type === "compact"){

        }
        else {
            var xAxis_g = svgContainer.append("g")
            .attr("class", "x axis")
            .attr("transform", "translate(0," + (height) + ")")
            .call(xAxis)
            .selectAll("text")
            .attr("y", -14)
            .attr("x", -10)
            .attr("dy", "2em")
            .attr("transform", "rotate(-90)")
            .attr("id", function (d) {return "xlab_" + d})
            .style("text-anchor", "end")
            .on("mouseover", function (d) {
                d3.select("#bar_"+ d).each(function(v, i) {
                    mouseover_bar(v);
                    d3.select(this).attr("opacity", '.80');
                })
            })
            .on("mouseout", function (d) {
                d3.select("#bar_"+ d).each(function(v, i) {
                    mouseout_bar(v);
                    var color_d =  color_schema.filter(function(w){ return w.name === v.kingdom; })[0];
                    d3.select(this).attr("opacity", '1');
                })
            });
        }


        svgContainer.selectAll(".bar")
            .data(data)
            .enter()
            .append("rect")
            .attr("id", function (d) {return "bar_" + d.uniprot_species_code})
            .attr("class", "bar")
            .attr("x", function (d) {
                return xScale(d.uniprot_species_code);
            })
            .attr("width", xScale.rangeBand())
            .attr("y", function (d) {
                return yScale(d.prots);
            })
            .attr("fill", function (d) {
                var color_d =  color_schema.filter(function(v){ return v["name"] === d.kingdom; })[0];
                return color_d ? color_d.color : "rgb(255,0,0)"
            })
            .attr("height", function (d) {
                return height - yScale(d.prots)
            })
            .on("mouseover", function (d) {

                mouseover_bar(d);

            })
            .on("mouseout", function (d) {
                mouseout_bar(d);
            });

        var yAxis_g = svgContainer.append("g")
            .attr("class", "y axis")
            .call(yAxis)
            .selectAll("text")
            .attr("y", -2)
            .attr("x", 9)
            .attr("dy", "-.15em")
            .attr("transform", "rotate(-90)")
            .style("text-anchor", "end");



        svgContainer.append("g")
            .attr("class", "grid")
            .call(make_y_axis()
                .tickSize(-width, 0, 0)
                .tickFormat("")
            );

        function mouseover_bar(d){
            d3.select("#xlab_"+ d.uniprot_species_code).each(function(v, i) {
                    d3.select(this).style("font-weight", "bold");
                });
                tooltip.transition()
                    .duration(200)
                    .style("opacity", .95);
                tooltip.html("<b>" + d.sciname.species + "</b> "+ d.sciname.strain+"</br><b>" + d.uniprot_species_code
                    + ", " + d.prots + "</b>")
                    .style("left", (d3.event.pageX + 5) + "px")
                    .style("top", (d3.event.pageY - 60) + "px");
        }

        function mouseout_bar(d){
            d3.select("#xlab_"+ d.uniprot_species_code).each(function(v, i) {
                        d3.select(this)
                            .style("font-weight", "");
                });
                tooltip.transition()
                    .duration(500)
                    .style("opacity", 0);
        }

        function add_legend(div_id) {

            // Legend part

            var svgLegend = d3.select("#" + div_id).append("svg")
                .attr("width", 800)
                .attr("height", 100)
                .append("g").attr("class", "container")
                .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

            // draw legend
            var legend = svgContainer.selectAll(".legend")
                .data([{
                    name: "Archaea",
                    color: "#ecf0f1"
                },
                    {
                        name: "Bacteria",
                        color: "#bdc3c7"
                    },
                    {
                        name: "Eukaryota",
                        color: "#7f8c8d"
                    },
                    {
                        color: "#2c3e50",
                        name: "_default"
                    }])
                .enter().append("g")
                .attr("class", "legend")
                .attr("transform", function (d, i) {
                    return "translate(0," + i * 20 + ")";
                });

            // draw legend colored rectangles
            legend.append("rect")
                .attr("x", width - 18)
                .attr("width", 18)
                .attr("height", 18)
                .style("fill", function (d) {
                    return d.color
                });

            // draw legend text
            legend.append("text")
                .attr("x", width - 24)
                .attr("y", 9)
                .attr("dy", ".35em")
                .style("text-anchor", "end")
                .text(function (d) {
                    return d.name;
                })

        }

    })

}
