class SyntenyViewer {

    constructor(div_id) {

        // MODEL
        this.contigs = []; // Contigs from JSON with linear array of hogs and edges

        //VIEWER
        this.viewer_data = null; // Contigs organised by rows for rendering
        this.unit_per_row = null;
        this.div_id = div_id;
        this.div = document.getElementById(this.div_id);

        // CONTROLLER

        this.settings = {
            level: null,
            width: this.div.offsetWidth,
            height: null,
            margin: {top: 64, right: 20, bottom: 16, left: 20},
            contig: {padding_top: 16, padding_right: 8, padding_bottom: 16, padding_left: 8, margin_bottom:64},
            row: {
                margin_bottom: 24, margin_right: 8, margin_left: 8, text_width: 24,
                base_start: 0, base_end: 24, bar_width: 8, bar_height: 30, min_bar_height: 10, edge_width: 12
            },
        }
        this.callback_click_hog = null
        this.color_accessor_hog = 'completeness_score';

    }

    // MODEL
    add_data(json) {

        /* This fn take the inputted json and extract the linear representation of the synteny (hogs and edges) */

        for (const key in json) {

            if (json[key]['nodes'].length === 1) {
                continue;
            }

            var current_contig = json[key];
            var nodes = current_contig['nodes'];
            var edges = current_contig['links'];

            var contig = {
                "linear_synteny": [],
                "hogs": {},
                "links": [],
                "rows": [],
                "number_hogs": nodes.length,
            }

            for (const nodesKey in nodes) {

                var hog = nodes[nodesKey]

                hog.neighbors = [];
                hog.edges = {};

                contig.hogs[hog.id] = hog

            }

            for (const edgesKey in edges) {

                var edge = edges[edgesKey];

                var target_hog = contig.hogs[edge['target']];
                var source_hog = contig.hogs[edge['source']];

                contig.links.push(edge);

                target_hog.neighbors.push(source_hog);
                target_hog.edges[source_hog] = edge
                source_hog.neighbors.push(target_hog);
                source_hog.edges[target_hog] = edge

            }

            // SANITY CHECK

            var ends = [];

            for (const hogsKey in contig.hogs) {

                var h = contig.hogs[hogsKey];

                switch (Object.keys(h.neighbors).length) {
                    case 0:
                        throw "No neighbor in this hog";
                    case 1:
                        ends.push(h);
                        if (ends.length > 2) {
                            throw "More than 2 ends in the contigs";
                        }
                        break;
                    case 2:
                        break;
                    default:
                        throw "More than 2 neighboring hogs"
                }

            }

            if (ends.length !== 2) {
                throw "Contigs dont have 2 ends."
            }

            // Flatten contig
            var previous = null
            var current = ends[0]
            var processing = true


            while (processing) {

                contig.linear_synteny.push(current);

                if (previous != null && current.neighbors.length === 1) {
                    previous = current;
                    current = current.neighbors[0];
                    processing = false;
                } else {
                    let tmp = current
                    current = current.neighbors[0] === previous ? current.neighbors[1] : current.neighbors[0];
                    previous = tmp;
                }

                previous.edge = previous.edges[current];


            }

            this.contigs.push(contig);

        }

    }

    // VIEWER

    _handleZoom(e) {
        d3.select('#master_g')
            .attr('transform', e.transform);
    }

    _calculate_unit_per_row(board_width) {
        this.unit_per_row = parseInt(board_width / (this.settings.row.bar_width + this.settings.row.edge_width));
    }

    _calculate_height(){

        var estimated_height = 0

        for (const contigKey in this.viewer_data) {
            var contig = this.viewer_data[contigKey];
            estimated_height += contig["rows"].length * (this.settings.row.bar_height + this.settings.row.margin_bottom) + this.settings.contig.margin_bottom + 2;
        }

        this.settings.height = estimated_height + this.settings.margin.bottom;

    }

    render() {

        this.contig_width = this.settings.width - this.settings.margin.left - this.settings.margin.right;
        this.contig_left_offset = this.settings.margin.left;
        this.row_width = this.contig_width - this.settings.row.margin_right - this.settings.row.margin_left;
        this.row_left_offset =  this.settings.margin.left + this.settings.row.margin_left
        this.board_width = this.row_width - this.settings.row.base_start - this.settings.row.base_end - 2 * this.settings.row.text_width;
        this.board_left_offset = this.settings.row.base_start + this.settings.row.text_width;


        this._calculate_unit_per_row(this.board_width);

        this._build_viewer_data();

        this._calculate_height();

        // Create the main svg with zoom
        const svg = d3.create("svg")
            .attr("viewBox", [0, 0, this.settings.width, this.settings.height])

        /*
        let zoom = d3.zoom()
            .scaleExtent([1, 5])
            .translateExtent([[0, 0], [this.settings.width, this.settings.height]])
            .on('zoom', this._handleZoom);

        svg.call(zoom);

        */

        this.Tooltip = d3.select("#" + this.div_id).append("div")
            .style("opacity", 0)
            .attr("class", "tooltip")
            .style("background-color", "white")
            .style("border", "solid")
            .style("border-width", "1px")
            .style("border-radius", "4px")
            .style("padding", "8px")
            .style("position", "absolute")
            .style("font-family", 'Roboto Condensed')
            .style("font-size", '16px')

        this.y_offset = this.settings.margin.top;
        this.master_g = svg.append("g").attr("id", 'master_g');

        var g_header = svg.append("g").attr('width', this.settings.width)

        g_header.append("text")
            .text("Synteny reconstruction for ancestral genome at " + this.settings.level)
            .attr("text-anchor", 'start')
            .attr("font-family", 'Roboto Condensed')
            .attr("font-size", '24px')
            .attr("x", this.contig_left_offset - 8)
            .attr("y", this.settings.margin.top/2)
            .style("stroke-width", 0)


        for (const contigKey in this.viewer_data) {

            var contig = this.viewer_data[contigKey];

            var contig_g = this._render_contig(contig);

            // todo use interpolate ?
            this.color_hog =  d3.scaleThreshold()
                .domain([contig.mean_completeness*0.2, contig.mean_completeness*0.4, contig.mean_completeness*0.6,contig.mean_completeness*0.8])
                .range(['#F08080', '#F8AD9D', 'lightgray', 'gray', 'dimgray']);

            this.color_edge =  d3.scaleThreshold()
                .domain([contig.mean_weight*0.2, contig.mean_weight*0.4, contig.mean_weight*0.6,contig.mean_weight*0.8])
                .range(['#F08080', '#F8AD9D', 'lightgray', 'gray', 'dimgray']);

            this.color_edge =  d3.scaleThreshold()
                .domain([contig.mean_weight*0.2, contig.mean_weight*0.4, contig.mean_weight*0.6,contig.mean_weight*0.8])
                .range(['#F08080', '#F8AD9D', 'lightgray', 'gray', 'dimgray']);

            this.height_bar = d3.scaleLinear()
                .domain([contig.min_size_hogs_no_outliers, contig.max_size_hogs_no_outliers])
                .range([this.settings.row.min_bar_height, this.settings.row.bar_height])
                .clamp(true);

            for (const rowKey in contig["rows"]) {

                var row = contig["rows"][rowKey];

                var g_row = this._render_row(contig_g, rowKey );

                var end = contig["rows"].length -1 == rowKey;

                for (const hogKey in row){

                    var hog = row[hogKey];

                    var edge = false;

                    if (hogKey < row.length ){
                        edge = hog.edge

                        if (edge == undefined){
                            console.log(hog)
                        }
                    }

                    var end_row = row.length -1 == hogKey;

                    this._render_hog_unit(hog, g_row, hogKey, edge, contig.mean_size_hogs, contig.mean_weight);

                }

                this._render_end_row(g_row, row.length, rowKey, end );

                this._render_start_row(g_row , rowKey);


            }


        }


        this.div.append(svg.node());


    }

    _render_contig(d){

        var g = this.master_g.append("g")
            .attr("class", "g_contig")
            .attr("width", this.contig_width)
            .attr("height", d["rows"].length * (this.settings.row.bar_height + this.settings.row.margin_bottom))
            .attr("transform", (v) => {
                var e = "translate(" + this.contig_left_offset + ", " + this.y_offset + ")";
                this.y_offset += d["rows"].length * (this.settings.row.bar_height + this.settings.row.margin_bottom) + this.settings.contig.margin_bottom + 2;
                return e;
            })

        g.append("rect")
            .attr("x", 0)
            .attr("y", 0)
            .attr("height", (e, i) => d["rows"].length * (this.settings.row.bar_height + this.settings.row.margin_bottom) + this.settings.contig.padding_bottom)
            .attr("width", this.contig_width)
            .style("fill", "none")
            .style("stroke", "none")


        g.append("line")
            .style("stroke", "lightgrey")
            .style("stroke-width", 1)
            .attr("x1", 0)
            .attr("y1", 0)
            .attr("x2", 0)
            .attr("y2", d["rows"].length * (this.settings.row.bar_height + this.settings.row.margin_bottom) + this.settings.contig.padding_bottom)



        g.append("line")
            .style("stroke", "lightgrey")
            .style("stroke-width", 1)
            .attr("x1", this.contig_width)
            .attr("y1", 0)
            .attr("x2", this.contig_width)
            .attr("y2", d["rows"].length * (this.settings.row.bar_height + this.settings.row.margin_bottom) + this.settings.contig.padding_bottom)



        return g


    }

    _render_row(parent, i){

        var tx = this.row_left_offset  ;
        var ty = i * (this.settings.row.bar_height + this.settings.row.margin_bottom)  ;

        return parent.append("g").attr("transform", () => {return "translate(" + tx + ", " + ty  + ")"})

    }

    _render_hog_unit(hog, g_container, i, edge, mean_size, mean_weight){

        var h_bar = this.height_bar(hog['nr_members']);

        var _this = this


        var r = g_container.append("rect")
            .attr("x", this.board_left_offset + i * (this.settings.row.bar_width + this.settings.row.edge_width))
            .attr("y", this.settings.contig.padding_top + (this.settings.row.bar_height - h_bar)/2)
            .attr("width", this.settings.row.bar_width)
            .attr("height",h_bar )
            .attr("fill",  this.color_hog(hog[this.color_accessor_hog]))
            .style("stroke-width", 1)
            .style("stroke", "white" )
            .on("mouseover",function () {
                _this.Tooltip.style("opacity", 1).style("display", 'block')
            })
            .on("mousemove", function (e)  {
                _this.Tooltip
                    .html(`<b>ID:</b> ${hog.id} <br> <b>Completeness:</b> ${hog.completeness_score.toFixed(3)} <br>  <b># of members:</b> ${hog.nr_members} `)
                    .style("left", e.pageX + 12 + "px")
                    .style("top", e.pageY + 12  + "px")
            })
            .on("mouseleave", function () {
                _this.Tooltip.style("opacity", 0).style("display", 'none')

            })

            if (this.callback_click_hog){
                r.style("cursor", "pointer")
                .on("click", () => {
                    this.callback_click_hog(hog)
                })
            }






        if (edge) {

            g_container.append("line")
                .attr("x1", this.settings.row.bar_width + this.board_left_offset + i * (this.settings.row.bar_width + this.settings.row.edge_width))
                .attr("y1",  this.settings.contig.padding_top + this.settings.row.bar_height / 2)
                .attr("x2",  this.settings.row.bar_width + this.board_left_offset + this.settings.row.edge_width + i * (this.settings.row.bar_width + this.settings.row.edge_width))
                .attr("y2", this.settings.contig.padding_top + this.settings.row.bar_height / 2)
                .style("stroke", this.color_edge(edge.weight)  )
                .style("stroke-width", edge.weight < 0.6 * mean_weight ? 2 : 3)
                .on("mouseover",function () {
                    _this.Tooltip.style("opacity", 1).style("display", 'block')
                })
                .on("mousemove", function (e)  {
                    _this.Tooltip
                        .html(`<b>Weight: </b> ${edge.weight} <br> `)
                        .style("left", e.pageX + 12 + "px")
                        .style("top", e.pageY + 12  + "px")
                })
                .on("mouseleave", function () {
                    _this.Tooltip.style("opacity", 0).style("display", 'none')

                })

        }


    }

    _render_end_row(g_container, unit, row_i, end){

        var off_x = this.settings.row.bar_width + this.board_left_offset + (unit-1)  * (this.settings.row.bar_width + this.settings.row.edge_width)


        if (end){
            g_container.append("g").append("line")
                .attr("x1", (d, i) => this.settings.row.bar_width + this.board_left_offset + (unit-1)  * (this.settings.row.bar_width + this.settings.row.edge_width))
                .attr("y1", (d) => this.settings.contig.padding_top + this.settings.row.bar_height / 2)
                .attr("x2", (d, i) => this.settings.row.bar_width + this.board_left_offset + this.settings.row.edge_width + (unit-1)  * (this.settings.row.bar_width + this.settings.row.edge_width))
                .attr("y2", (d) => this.settings.contig.padding_top + this.settings.row.bar_height / 2)
                .style("stroke", "gray")
                .style("stroke-width", 2)
                .style("stroke", "darkgray")

        }

        // Add start position

        g_container.append("text")
            .text(   parseInt(row_i) *  this.unit_per_row + unit  )
            .attr("text-anchor", 'start')
            .attr("font-size", '12px')
            .attr("x", (d, i) => this.settings.row.edge_width + 4 + this.settings.row.bar_width + this.board_left_offset + (unit-1)  * (this.settings.row.bar_width + this.settings.row.edge_width))
            .attr("y", (d) => this.settings.contig.padding_top + this.settings.row.bar_height /2 + 4)
            .style("stroke-width", 0)
            .attr("font-family", 'Roboto Condensed')


        // Add start base symbol
        var t = d3.symbol().type(d3.symbolTriangle).size(24);
        var c = d3.symbol().type(d3.symbolCircle).size(12);

        g_container.append("g")
            .attr("transform", "translate(" + (off_x + this.settings.row.edge_width) + "," + (this.settings.contig.padding_top + this.settings.row.bar_height / 2) + ")")
            .append("path")
            .attr("d", end ? t() : c() )
            .attr("transform", "rotate(150)")
            .attr("stroke-width", 0)


    }

    _render_start_row(g_container, i){

        // Add start base line
        g_container.append("line")
            .style("stroke", "darkgray")
            .style("stroke-width", 2)
            .attr("x1",  this.board_left_offset - this.settings.row.edge_width)
            .attr("y1", this.settings.contig.padding_top + this.settings.row.bar_height / 2)
            .attr("x2", this.board_left_offset)
            .attr("y2", this.settings.contig.padding_top + this.settings.row.bar_height / 2)


        // Add start base symbol
        var t = d3.symbol().type(d3.symbolTriangle).size(24);
        var c = d3.symbol().type(d3.symbolCircle).size(12);


        g_container.append("g")
            .attr("transform", "translate(" + (this.board_left_offset - this.settings.row.edge_width) + "," + (this.settings.contig.padding_top + this.settings.row.bar_height / 2) + ")")
            .append("path")
            .attr("d", i == 0 ? t() : c() )
            .attr("transform", "rotate(-30)")
            .attr("stroke-width", 0)
            .attr("stroke", "darkgray")


        // Add start position
        g_container.append("text")
            .attr("transform", "translate(" + (this.board_left_offset - this.settings.row.edge_width - 4) + "," + (this.settings.contig.padding_top + this.settings.row.bar_height / 2 + 4) + ")")
            .text( i * this.unit_per_row + 1)
            .attr("text-anchor", 'end')
            .attr("font-size", '12px')
            .attr("stroke-width", 0)
            .attr("font-family", 'Roboto Condensed')


    }

    _build_viewer_data() {

        /*
        build viewer_data from contigs by organising contigs in rows
         */


        var datum = []

        for (const contigKey in this.contigs) {

            var c = this.contigs[contigKey];

            var contig_d3 = {
                "rows": [],
                "min_size_hogs_no_outliers" : null,
                "max_size_hogs_no_outliers" : null,
                "mean_completeness" : null,
                "mean_size_hogs" : null,
                "mean_weight" : null,
            }


            for (let i = 0; i < c.linear_synteny.length; i += this.unit_per_row) {
                contig_d3["rows"].push(c.linear_synteny.slice(i, i + this.unit_per_row));
            }

            var sizes = [];
            var compl = [];
            var weight = [];
            for (let i = 0; i < c.linear_synteny.length; i++) {
                sizes.push(c.linear_synteny[i]["nr_members"]);
                compl.push(c.linear_synteny[i]["completeness_score"]);
                weight.push(c.linear_synteny[i]["edge"]["weight"]);
            }

            contig_d3.min_size_hogs = Math.min(...sizes);
            contig_d3.max_size_hogs = Math.max(...sizes);

            var sizes_out = this.filterOutliers(sizes);

            if (sizes_out.length > 0 ) {
                contig_d3.min_size_hogs_no_outliers = Math.min(...sizes_out);
                contig_d3.max_size_hogs_no_outliers = Math.max(...sizes_out);
            }
            else{
                contig_d3.min_size_hogs_no_outliers = contig_d3.min_size_hogs
                contig_d3.max_size_hogs_no_outliers = contig_d3.max_size_hogs
            }


            contig_d3.mean_completeness = (compl.reduce((a, b) => a + b, 0) / compl.length) || 0; // this.mode(compl) //
            contig_d3.mean_size_hogs = this.mode(sizes) // (sizes.reduce((a, b) => a + b, 0) / sizes.length) || 0;
            contig_d3.mean_weight =  (weight.reduce((a, b) => a + b, 0) / weight.length) || 0;

            datum.push(contig_d3);

        }

        this.viewer_data = datum;

    }

    // CONTROLLER
    configure(settings) {

        for (const settingsKey in settings) {
            this.settings[settingsKey] = settings[settingsKey];

        }

    }

    // UTILS
    mode(arr)  {
        const mode = {};
        let max = 0, count = 0;

        for(let i = 0; i < arr.length; i++) {
            const item = arr[i];

            if(mode[item]) {
                mode[item]++;
            } else {
                mode[item] = 1;
            }

            if(count < mode[item]) {
                max = item;
                count = mode[item];
            }
        }

        return max;
    };

    filterOutliers(someArray) {

        // Copy the values, rather than operating on references to existing values
        var values = someArray.concat();

        // Then sort
        values.sort( function(a, b) {
            return a - b;
        });

        /* Then find a generous IQR. This is generous because if (values.length / 4)
         * is not an int, then really you should average the two elements on either
         * side to find q1.
         */
        var q1 = values[Math.floor((values.length / 4))];
        // Likewise for q3.
        var q3 = values[Math.ceil((values.length * (3 / 4)))];
        var iqr = q3 - q1;

        // Then find min and max values
        var maxValue = q3 + iqr*1.5;
        var minValue = q1 - iqr*1.5;

        // Then filter anything beyond or beneath these values.
        var filteredValues = values.filter(function(x) {
            return (x <= maxValue) && (x >= minValue);
        });

        // Then return
        return filteredValues;
    }

}


