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
            target: null,
            error_target: null,
            type: null,
            width: this.div.offsetWidth,
            height: null,
            margin: {top: 64, right: 20, bottom: 16, left: 20},
            contig: {padding_top: 16, padding_right: 8, padding_bottom: 16, padding_left: 8, margin_bottom:64},
            row: {
                margin_bottom: 24, margin_right: 8, margin_left: 8, text_width: 24,
                base_start: 0, base_end: 24, bar_width: 8, bar_height: 30, min_bar_height: 10, edge_width: 12
            },
        }
        this.callback_click_detail = null
        this.callback_click_synteny = null
        this.callback_click_members = null

        this.color_accessor_hog = 'completeness_score';
        this.color_remove_outlier_hog = true;

        this.color_accessor_edge = 'weight';
        this.color_remove_outlier_edge = true;

        this.height_accessor_hog = 'nr_members';
        this.height_remove_outlier_hog = true;


        this.selected_element = null;
        this.target_element = null;

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
            var current = ends.sort((a, b) => a.id.toLowerCase().localeCompare(b.id.toLowerCase()))[0];
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

    _settings_HOGs(){

        var check_hei = this.height_remove_outlier_hog ? 'checked' : ''
        var check_col = this.color_remove_outlier_hog ? 'checked' : ''


        return `
         
         <p class='ui_title' > HOGs</p>
        
        <div class='ui_div' > 
            <p class='ui_text' ><b>Height</b></p>
            <span>
            <select name=""  id="selecthhei">
            <option value="nr_members" selected ># Members</option>
            <option value="completeness_score">Completeness</option>
            </select>
            </span>
            <span style="display: block">
            <input id='outlier_hog_height' type="checkbox" ${check_hei} > <label for="">Remove outliers</label>
            </span>
        </div>
        
       
        <div class='ui_div'> 
            <p class='ui_text' ><b>Coloring</b></p>
            <span><select name="" id="selecthcol">
            <option value="nr_members"># Members</option>
            <option value="completeness_score" selected >Completeness</option>
            </select></span>
            <span style="display: block"><input id='outlier_hog_coloring' type="checkbox" ${check_col} > <label for="">Remove outliers</label></span>
        </div>
        `
    }

    _bind_ui_hog(){


        document.getElementById("selecthhei").onchange = (e) => {

            this.height_accessor_hog = e.target.value;
            this.render()

        }

        document.getElementById("selecthcol").onchange = (e) => {

            this.color_accessor_hog = e.target.value;
            this.render()

        }


        document.getElementById("outlier_hog_height").addEventListener('change', (event) => {
            this.height_remove_outlier_hog = event.currentTarget.checked ? true : false;
            this.render()
        })

        document.getElementById("outlier_hog_coloring").addEventListener('change', (event) => {
            this.color_remove_outlier_hog = event.currentTarget.checked ? true : false;
            this.render()
        })

    }

    _settings_Edges(){

        return `
           
        <p class='ui_title'> Edges</p>
        
   
        <div class='ui_div'> 
            <p class='ui_text' ><b>Coloring</b></p>
            <span><select name="" id="selectecol">
            <option value="Weight">Weight</option>
            </select></span>
            <span style="display: block"><input id='outlier_edge_coloring' type="checkbox" checked> <label for="">Remove outliers</label></span>
        </div>
        `

    }

    _bind_ui_edge(){

        document.getElementById("selectecol").onchange = (e) => {

            this.color_accessor_edge = e.target.value;
            this.render()

        }



        document.getElementById("outlier_edge_coloring").addEventListener('change', (event) => {
            this.color_remove_outlier_edge = event.currentTarget.checked ? true : false;
            this.render()
        })


    }

    _build_interface(){


        d3.select('.corner_placeholder').remove()


        this.UI_container_search = d3.select(this.div).append("div").attr("class","corner_placeholder top right")
            .style("flex-direction",'row')
            .style("align-items",'end')
            .style('margin-right', '66px')
        .style( 'margin-top', '10px')

         // INPUT SEARCH
        this.search = this.UI_container_search.append("div").style("display",'flex').append("input")
            .attr("type", "text")
            .attr("id", "search_geneorder")
            .attr("placeholder", () => this.settings.type == 'ancestral' ? " Search for hog/gene..." :  " Search for gene...")
            .style( 'height', '40px')

        var s_b = this.UI_container_search.append('button')
                .attr('id', 'button_search')
                .attr('class', ' square_button')
                .style( 'height', '40px')


            s_b.append("div")
                .attr("class", "label")
                .append('i')
                .style('color', '#888')
                .attr('class', ' fas fa-search')



        s_b.on("click", d => {

            var base = window.location.href.split('?target=')[0]
            var query = '?target=' + document.getElementById("search_geneorder").value;
            window.location.replace(base + query);
        })



        if (this.settings.type == 'ancestral') {

            this.UI_container = d3.select(this.div).append("div").attr("class","corner_placeholder top right")
            .style("flex-direction",'column')
            .style("align-items",'end')

            this.tr_buttons = this.UI_container.append("div").attr("class", "tr-button").style("display", 'flex')

            this.tr_menus = this.UI_container.append("div").attr("class", "tr-menus")

            // BUTTON
            var ex_b = this.tr_buttons.append('button')
                .attr('id', 'button_settings')
                .attr('data-bs-placement', 'bottom')
                .attr('title', 'Configure viewer appearance')

            var divybuty = ex_b.attr('class', ' square_button')
                .style('margin', '2px')
                .on("click", d => {
                    if (this.menu_export.style('display') === 'none') {
                        return this.menu_export.style("display", 'block')
                    }
                    this.menu_export.style("display", 'none')
                })

            divybuty.append("div")
                .attr("class", "label")
                .append('i')
                .style('color', '#888')
                .attr('class', ' fas fa-cog ')

            divybuty.append('p')
                .text('Settings')
                .style('font-size', 'xx-small')

            this.tooltip_export = new bootstrap.Tooltip(document.getElementById('button_settings'))

            // UI MENU
            this.menu_export = this.tr_menus.append('div').attr('class', 'menu_export')

            // HOG
            this.menu_export.append("div").html(this._settings_HOGs())
            this._bind_ui_hog();

            // EDGE
            this.menu_export.append("div").html(this._settings_Edges())
            this._bind_ui_edge();

        }


    }

    render() {

        d3.select("svg").remove();

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
        this.svg = d3.create("svg")
            .attr("viewBox", [0, 0, this.settings.width, this.settings.height])

        this._build_interface();


        this.Tooltip = d3.select("#" + this.div_id).append("div")
            .style("opacity", 0)
            .attr("class", "tooltip")
            .style("background-color", "white")
            .style("border", "solid")
            .style("border-width", "1px")
            .style("border-radius", "4px")
            .style("padding", "8px")
            .style("position", "absolute")
            .style("font-size", '16px')
            .style("z-index", '999')

        this.y_offset = this.settings.margin.top;
        this.master_g = this.svg.append("g").attr("id", 'master_g');

        var g_header = this.svg.append("g").attr('width', this.settings.width)

        g_header.append("text")
            .text((this.settings.type === "ancestral" ? "Ancestral gene order reconstruction " : "Gene order ") +
                " for " + this.settings.level +" genome")
            .attr("text-anchor", 'start')
            .attr("font-size", '24px')
            .attr("x", this.contig_left_offset - 8)
            .attr("y", () => this.settings.target != 'null' || this.settings.error_target != 'null' ? this.settings.margin.top/4 :  this.settings.margin.top/2)
            .style("stroke-width", 0)

        if (this.settings.target != 'null' || this.settings.error_target != 'null' ){


            var msg = this.settings.error_target != 'null'  ? this.settings.error_target : "Focus: " + this.settings.target + ' (<a style="display:inline" fill="steelblue"  id="click_to_scroll" >click to scroll</a>)'

            g_header.append("text")
            .html(msg)
            .attr("text-anchor", 'start')
            .attr("font-size", '16px')
                .attr('fill', () =>  this.settings.error_target == 'null'  ? '#888' : 'salmon' )
            .attr("x", this.contig_left_offset - 8)
            .attr("y", this.settings.margin.top/2)
            .style("stroke-width", 0)

        }



        for (const contigKey in this.viewer_data) {

            var contig = this.viewer_data[contigKey];

            // check if contigKey is number, in which case we use this one (+1)
            let contig_nr = (contigKey == parseInt(contigKey, 10) ? parseInt(contigKey, 10) + 1 : contigKey)
            var contig_g = this._render_contig(contig, contig_nr);

             if (this.settings.type == 'ancestral') {

                 var color_hog = this.color_remove_outlier_hog ? contig[this.color_accessor_hog].mean_no_out : contig[this.color_accessor_hog].mean
                 this.scale_color_hog = d3.scaleThreshold()
                     .domain([color_hog * 0.2, color_hog * 0.4, color_hog * 0.6, color_hog * 0.8])
                     .range(['#F08080', '#F8AD9D', 'lightgray', 'gray', 'dimgray']);

                 var color_edge = this.color_remove_outlier_edge ? contig[this.color_accessor_edge].mean_no_out : contig[this.color_accessor_edge].mean
                 this.scale_color_edge = d3.scaleThreshold()
                     .domain([color_edge * 0.2, color_edge * 0.4, color_edge * 0.6, color_edge * 0.8])
                     .range(['#F08080', '#F8AD9D', 'lightgray', 'gray', 'dimgray']);

                 var min_height_hog = this.height_remove_outlier_hog ? contig[this.height_accessor_hog].min_no_out : contig[this.height_accessor_hog].min
                 var max_height_hog = this.height_remove_outlier_hog ? contig[this.height_accessor_hog].max_no_out : contig[this.height_accessor_hog].max

                 this.scale_height_hog = d3.scaleLinear()
                     .domain([min_height_hog, max_height_hog])
                     .range([this.settings.row.min_bar_height, this.settings.row.bar_height])
                     .clamp(true);

             }


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

                    this._render_element_unit(hog, g_row, hogKey, edge, contig[this.color_accessor_edge].mean);

                }

                this._render_end_row(g_row, row.length, rowKey, end );

                this._render_start_row(g_row , rowKey);


            }


        }


        this.div.append(this.svg.node());

        var scroll_b = document.getElementById('click_to_scroll');

        if (scroll_b !== null) {
            scroll_b.addEventListener('click', () => {
            console.log('click')
            this.scroll_to_target();
        })
            }






    }

    _render_contig(d, nr){

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


        let chr_title;
        if (this.settings.type == 'extant') {
            chr_title = "Chromosome " + d["rows"][0][0]['chromosome'];
        } else {
            chr_title = "Ancestral contig " + nr;
        }
        g.append("text")
        .text(chr_title)
        .attr("text-anchor", 'start')
        .attr("font-size", '12px')
        .attr("x", this.contig_left_offset)
        .attr("y", 0)
        .style("stroke-width", 0)
        .attr("font-family", 'Roboto Condensed')

        return g

    }

    _render_row(parent, i){

        var tx = this.row_left_offset  ;
        var ty = i * (this.settings.row.bar_height + this.settings.row.margin_bottom)  ;

        return parent.append("g").attr("transform", () => {return "translate(" + tx + ", " + ty  + ")"})

    }

    _render_element_unit(hog, g_container, i, edge, mean_weight){

        var h_bar;

        if (this.settings.type == 'ancestral'){
             h_bar = this.scale_height_hog(hog['nr_members']);
         }
         else {
            h_bar = this.settings.row.bar_height
         }

        var _this = this


        var r = g_container.append("rect")
            .attr("x", this.board_left_offset + i * (this.settings.row.bar_width + this.settings.row.edge_width))
            .attr("y", this.settings.contig.padding_top + (this.settings.row.bar_height - h_bar)/2)
            .attr("width", this.settings.row.bar_width)
            .style("cursor", "pointer")
            .attr("height",h_bar )
            .attr("fill",  () => {return _this.settings.type == 'ancestral' ? this.scale_color_hog(hog[this.color_accessor_hog]) : 'gray' })
            .style("stroke-width", 1)
            .style("stroke", "white" )
            .on("click", (event, node) => {

                if(this.selected_element){
                         this.selected_element.style("stroke-width", 1)
                         this.selected_element.style("stroke", "white")
                         this.selected_element = null
                    }

                this.selected_element = d3.select(event.target)
                this.selected_element.style("stroke-width", 2)
                this.selected_element.style("stroke", "red")


                var menu = [];
                var data_annotation = null;

                menu.push( { title: '<b>' + hog.id +'</b>', action: null } )

                if (_this.settings.type == 'ancestral'){

                    var level_api = _this.settings.level ? '?level=' + _this.settings.level : ''

                    $.ajax({
                        url: "/api/hog/"+ hog.id +"/" + level_api,
                        dataType: 'json',
                        async: false,
                        success: function (data) {
                            menu.push( { title: '<b>Description: </b>' +  data[0].description, action: null } )
                            menu.push( { title: '<b>Completeness: </b>' + hog.completeness_score.toFixed(3), action: null } )
                            menu.push( { title: '<b>Nb of members: </b>' + hog.nr_members, action: null } )
                        }

                    })

                     menu.push({ title: '<a href=""> Open HOG detail </a>', action: () => {_this.callback_click_detail(hog.id) }})
                    menu.push({ title:  '<a href=""> Open HOG members </a>', action: () => {_this.callback_click_members(hog.id) }})
                     menu.push({ title:  '<a href=""> Open local synteny </a>',action: () => { _this.callback_click_synteny(hog.id) }})

                }

                else {

                    $.ajax({
                        url: "/api/protein/"+ hog.id +"/",
                        dataType: 'json',
                        async: false,
                        success: function (data) {

                            menu.push( { title: '<b>External Id:</b>' +  data.canonicalid, action: null } )
                            menu.push( { title: '<b>Sequence length:</b>' + data.sequence_length, action: null } )
                        }

                    })

                    menu.push({ title:  '<a href=""> Open Local Synteny </a>' , action: () => { _this.callback_click_synteny(hog.id) }})
                    menu.push({ title:  '<a href=""> Open Gene details </a>', action: () => {_this.callback_click_detail(hog.id) }})


                }

                menu.push({ title: 'Close', action: () => {  this.close_tooltip()}})

                menu.push({ title: ' <hr style="margin-top: 0.3em; margin-bottom: 0.1em"> ', action: null })
                menu.push({ title: ' <b>GO annotations</b>  <hr style="margin-top: 0.1em; margin-bottom: 0.2em"> ', action: null })

                var url = _this.settings.type == 'ancestral' ? "/api/hog/"+ hog.id +"/gene_ontology/" + level_api : "/api/protein/"+ hog.id +"/gene_ontology/"

                $.ajax({
                    url: url,
                    dataType: 'json',
                    async: false,
                    success: function (data_go) {data_annotation = data_go}
                })


                if (data_annotation){

                    var bio = new Set(); //  Biological Process
                    var cell = new Set(); // Cellular Component
                    var mol = new Set(); // Molecular Function

                    for (const contentKey in data_annotation) {

                        var go = data_annotation[contentKey]

                        switch (go.aspect) {

                            case "cellular_component":
                                cell.add(go);
                                break;
                            case 'biological_process':
                                bio.add(go);
                                break;
                            case 'molecular_function':
                                mol.add(go);
                                break;
                            default:
                                console.log(`${go.aspect} not recognise as annotation category.`);

                        }

                        }

                    var add_annotation_by_aspect = function(array_aspect, text){
                         var sbio = Array.from(array_aspect).sort(function(a, b) {return parseFloat(b.score) - parseFloat(a.score);})
                    menu.push( { title: '<b> ' + text + ' </b>: ' , action: null } )

                        for (var sbioKey in sbio) {
                        let go = sbio[sbioKey]
                       menu.push( { title: '<b> - ' + go.GO_term + '</b>: ' + go.name , action: null } )
                    }
                    }

                    add_annotation_by_aspect(bio, 'Biological Process')
                    add_annotation_by_aspect(cell, 'Cellular Component')
                    add_annotation_by_aspect(mol, 'Molecular Function')

                }

                //this.render_tooltip(event.offsetX + 12, event.offsetY + 12, menu)
                this.render_tooltip(event.pageX + 12, event.pageY + 12, menu)

            })

        if (this.settings.target == hog.id){
            this.target_element = r.node();
            r.attr("fill", "mediumseagreen" )
        }

        if (edge) {

            g_container.append("line")
                .attr("x1", this.settings.row.bar_width + this.board_left_offset + i * (this.settings.row.bar_width + this.settings.row.edge_width))
                .attr("y1",  this.settings.contig.padding_top + this.settings.row.bar_height / 2)
                .attr("x2",  this.settings.row.bar_width + this.board_left_offset + this.settings.row.edge_width + i * (this.settings.row.bar_width + this.settings.row.edge_width))
                .attr("y2", this.settings.contig.padding_top + this.settings.row.bar_height / 2)
                .style("stroke", () => { return _this.settings.type == 'ancestral' ? this.scale_color_edge(hog[this.color_accessor_edge]) : 'lightgray' })
                .style("stroke-width",  edge.weight < 0.6 * mean_weight ? 2 : 3)
                .on("mouseover",() =>  {

                    if(this.selected_element){
                         this.selected_element.style("stroke-width", 1)
                         this.selected_element.style("stroke", "white")
                         this.selected_element = null
                    }


                      if (this.settings.type == 'ancestral'){
                          this.Tooltip.style("opacity", 1).style("display", 'block')
                      }
                      else{
                          _this.Tooltip.style("opacity", 0).style("display", 'none')
                      }





                })
                .on("mousemove", function (e)  {

                     if (_this.settings.type == 'ancestral'){
                          _this.Tooltip
                        .html(`<b>Weight: </b> ${edge.weight} <br> `)
                        .style("left", e.pageX + 12 + "px")
                        .style("top", e.pageY + 12  + "px")
                      }

                })
                .on("mouseleave", function () {

                     if (_this.settings.type == 'ancestral'){
                          _this.Tooltip.style("opacity", 0).style("display", 'none')
                      }


                })

        }


    }

     render_tooltip(x, y, menu) {


        this.Tooltip.style("opacity", 1).style("display", 'block')
            .style("left", x + 12 + "px")
            .style("top", y + 12 + "px")

        this.Tooltip.html('')

        var gg = this.Tooltip.selectAll('menu_item')
            .data(menu)
            .enter().append('text')
            .style('text-align',(d) =>{ return d.action ? 'center' : 'left' } )
            .style('display', 'block')
            .style('cursor', (d) => {
                return d.action ? 'pointer' : 'auto'
            })
            .style("font-weight", (d) => {
                return d.title === "Close" || d.action ? 900 : 400
            })
            .style('font-size', d => {
                return '12 px';
            })
            .html(function (d) {
                return d.title;
            })
            .on('mouseover', function (d) {
                d3.select(this).style('fill', 'steelblue');
            })
            .on('mouseout', function (d) {
                d3.select(this).style('fill', 'black');
            })
            .on('click', function (d, i) {
                i.action(d);
            })


    }

     close_tooltip() {
        if (this.selected_element){
            this.selected_element.style("stroke-width", 1)
         this.selected_element.style("stroke", "white")

         this.selected_element = null
        this.Tooltip.style("opacity", 0).style("display", 'none')
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

            }


            for (let i = 0; i < c.linear_synteny.length; i += this.unit_per_row) {
                contig_d3["rows"].push(c.linear_synteny.slice(i, i + this.unit_per_row));
            }

            var sizes = [];
            var compl = [];
            var weight = [];
            for (let i = 0; i < c.linear_synteny.length; i++) {
                if (this.settings.type == 'ancestral'){
                    sizes.push(c.linear_synteny[i]["nr_members"]);
                compl.push(c.linear_synteny[i]["completeness_score"]);
                }

                weight.push(c.linear_synteny[i]["edge"]["weight"]);
            }

            if (this.settings.type == 'ancestral'){
               contig_d3.nr_members  = this.get_stat(sizes);
                contig_d3.completeness_score  = this.get_stat(compl);
            }

            contig_d3.weight  = this.get_stat(weight);


            datum.push(contig_d3);

        }

        this.viewer_data = datum;

    }

    // CONTROLLER
    configure(settings) {

        for (const settingsKey in settings) {
            this.settings[settingsKey] = settings[settingsKey];
        }

        if (this.settings.target != 'null'  || this.settings.error_target != 'null'){
            this.settings.margin.top  = this.settings.margin.top * 1.5;
        }

        console.log(this.settings.target ,this.settings.error_target)


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

    get_stat(array){

        var stat = {
            "min": null,
            "max": null,
            "min_no_out": null,
            "max_no_out": null,
            "mean": null,
            "mean_no_out": null,
        }

        stat.min = Math.min(...array);
        stat.max = Math.max(...array);

        var array_not_out = this.filterOutliers(array);

        if (array_not_out.length > 0 ) {
            stat.min_no_out = Math.min(...array_not_out);
            stat.max_no_out = Math.max(...array_not_out);
        }
        else{
            stat.min_no_out =  stat.min;
            stat.max_no_out = stat.max;
        }

        stat.mean =  (array.reduce((a, b) => a + b, 0) / array.length) || 0;
        stat.mean_no_out =  (array_not_out.reduce((a, b) => a + b, 0) / array_not_out.length) || 0;

        return stat

    }

    scroll_to_target(){

        if (this.target_element){

            console.log(this.target_element)
                this.target_element.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
            }

    }

}


