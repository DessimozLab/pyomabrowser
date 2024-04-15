var start = Date.now();
var millis = Date.now() - start;

/*

DEV MAP

ZOOM:
    - add g under each panel (like clipath) and add specific zoom to each element
e.g. zoom on matrix do all but paning on tree move the tree, etc..

GENE TREE:
     - zoom at max the name are y offset need to account for middle anchor
     - no gutter so crosshair is conitnous line neeed to remove one or 2 character for inner padding
     - Recalibrate ellipsis for gene name


 */

function defaultDict() {
    this.get = function (key) {
        if (this.hasOwnProperty(key)) {
            return this[key];
        } else {
            return 0;
        }
    }
}

class Hog_placement {

    constructor(div_id, data_species_tree) {

        // Settings
        this.cell_size = 30;
        this.gutter = 20;
        this.species_tree_width = 100;
        this.genes_tree_width = 200;
        this.gene_label_width = 100;
        this.species_label_width = 170;
        this.gene_name_width = 100;
        this.species_name_width = 100;
        this.start_collapse_depth= 10;
        this.max_depth = 0;
        this.show_image = true;
        this.min_width = 600;
        this.min_heigth = 600;
        this.node_color = "#999"
        this.color_cell_zero = "#f8f8f8"
        this.gene_name_padding_left = 5;
        this.leaf_font_size = 10
        this.zoom_transform = null;
        this.sub_sampling_ratio = 1;
        this.gene_name_padding_y = (this.cell_size - this.leaf_font_size) /2;
        this.crosshair_width = 2;
        this.gene_tree_x_translate = 0;
        this.old_transform = d3.zoomIdentity;


        // UTILS METRICS
        this.grid = null;

        // Data
        this.data_species_tree = data_species_tree;
        this.data_gene_tree_list = [];
        this.cols = null;

        this.data_gene_tree = null;
        this.rows = null;

        // Container
        this.container_id = div_id
        this.d3_container = d3.select("#" + this.container_id)
        this.container_size = this.d3_container.node().getBoundingClientRect()

    }

    start(){

        d3.select(".tooltip").remove()

        // build species tree hierarchy
        this._create_hierarchy_species();

        // Build gene tree hierarchy
        this._create_hierarchy_genes();

        // Create maste r SVG
        this._create_svg()

        // Render the viewers
        this._render()

        // initial zooming
        this._zoom_start()

        //document.getElementById('quantity').max = this.max_depth;
        //document.getElementById('quantity').value = this.start_collapse_depth;

        //this.add_legend()

        //this.start_collapse()

         // Add action to button
        /*
        d3.select("#expandB").on("click", () => {
            this.expandAll()

            this.data_matrix = this.build_matrix2()
            this.render()
            this.recalibrate_position()
        })


        d3.select("#collapseB").on("click", () => {
            this.expandAll()
            this.start_collapse()
            //this.data_matrix = this.build_matrix2()
            //this.render()
            //this.recalibrate_position()
        })

        d3.select("#smartB").on("click", () => {
            this.expandAll()
            this.smart_collapse()
        })


        d3.select("#show_species").on("click", () => {
            this.show_image = document.getElementById('show_species').checked;
            //console.log(this.show_image)
        })


        d3.select("#quantity").on("change", () =>  {

            this.start_collapse_depth = document.getElementById('quantity').value;

            this.hierarchy_species.eachBefore(d => {
                if (d._children) {
                    d.children = d._children
                    d._children = null;
                }
            })

            this.hierarchy_species.eachAfter(d => {

                if (this.start_collapse_depth <= d.depth){

                    if (d.children) {
                        d._children = d.children;
                        d.children = null;
                    }

                }


            })

            this.data_matrix = this.build_matrix2()
            this.render()
            this.recalibrate_position()


        })


         */


    }

    _create_hierarchy_species() {

        // Build species tree hierarchy
        this.hierarchy_species = d3.hierarchy(this.data_species_tree);

        var rootlist = this.data_gene_tree_list.map(hog => hog.taxon)

        var pruned_species_tree = null;
        var depth_off_set = null
        var found = null
        this.hierarchy_species.each(function(d) {

            if ( rootlist.includes(d.data.name) && !found ){
                pruned_species_tree = d;
                pruned_species_tree.parent = null
                depth_off_set = d.depth
                found= true
            }

        })

        this.hierarchy_species = pruned_species_tree ? pruned_species_tree : this.hierarchy_species

        this.max_depth = 0

        this.hierarchy_species.each(d => {

            d.depth = d.depth - depth_off_set;

            if (!d.data.description){d.data.description = ''}
            if (!d.data.taxon){d.data.taxon = d.data.name}
            if (!d.data.color){d.data.color = ''}
            if (!d.data.matrix_color){d.data.matrix_color = ''}

            if (d.depth > this.max_depth){
                this.max_depth = d.depth
            }

        })

         // CREATE LABELS COLOR SCALE
        var list_label = []
        this.hierarchy_species.each(d => {d.data.description ? list_label.push(d.data.description): null})
        var dsc = [new Set(list_label)];
        this.speciesColor = d3.scaleOrdinal().domain(dsc).range(d3.schemePaired);

    }

    _create_hierarchy_genes() {

        this.hierarchy_genes = d3.hierarchy(this.data_gene_tree);

        var list_label = []
        this.hierarchy_genes.each(d => {d.data.description ? list_label.push(d.data.description): null})
        var dgc = [new Set(list_label)];
        this.genesColor = d3.scaleOrdinal().domain(dgc).range(d3.schemePaired);
    }

    _create_svg(){

        d3.select("svg").remove();

        this.SVG = this.d3_container
            .append("svg")

        this.G =  this.SVG.attr("width", Math.max(this.min_width,this.container_size.width))
            .attr("height", Math.max(this.min_heigth,this.container_size.height))
            .append("g")

    }

     _grid_position(){

        this.grid = {
            'board_width':this.container_size.width - 4 * this.gutter -  this.gene_label_width -  this.gene_name_width - this.genes_tree_width,
            'board_height':this.container_size.height - 3 * this.gutter -  this.species_tree_width -  this.species_name_width,
            'startx_st':1*this.gutter + this.gene_name_width + this.genes_tree_width,
            'starty_st':this.gutter,
            'startx_gt':this.gutter,
            'starty_gt': 2*this.gutter + this.species_tree_width + this.species_name_width,
        }

        this.grid.startx_glabel = this.gutter + this.gene_name_width + this.genes_tree_width + this.grid.board_width;


    }

    _clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    _render() {

        d3.select('#g_species').remove()
        d3.select('#g_gene').remove()
        d3.select('#g_gene_g').remove()
        d3.select('#g_genes_labels').remove()
        d3.select('#g_genes_names').remove()
        d3.select('#g_matrix').remove()
        d3.select('#g_species_labels').remove()
        d3.select('#g_species_names').remove()

        this._grid_position();

        this._build_matrix()

        this._render_matrix()

        this._render_species_tree()

        this._render_species_names()

        this._render_gene_tree()

        this._render_genes_labels()

        this._render_genes_names()

        this._build_zoom()



    }

    _build_zoom(){

        this.zoom = d3.zoom()
            .on('zoom', (event) => {

                // Set extant of scale and translate
                //event.transform.x = this._clamp(event.transform.x, (-this.grid.board_width+20) / event.transform.k, (this.grid.board_width-20) / event.transform.k)
                //event.transform.y = this._clamp(event.transform.y, -this.grid.board_height+20, this.grid.board_height-20)
                event.transform.k  = this._clamp(event.transform.k, this.ratio_zoom, 5)
                this.zoom_transform = event.transform;

                // Compute label subsampling ratio
                this.sub_sampling_ratio = Math.ceil(this.leaf_font_size / (this.cell_size * this.zoom_transform.k));


                if (event.sourceEvent){
                    if (event.sourceEvent.offsetX < this.grid.startx_st){
                        this.gene_tree_x_translate +=  -event.sourceEvent.movementX
                        this.gene_tree_x_translate = this._clamp( this.gene_tree_x_translate, -this.grid.genes_tree_width_raw*this.zoom_transform.k+10, 0)
                        this.zoom_transform.x = this.old_transform.x;

                    }
                }

                // MATRIX
                var mat_tr = d3.zoomIdentity;
                mat_tr.x = this.zoom_transform.x;
                mat_tr.k = this.zoom_transform.k;
                mat_tr.y = this.zoom_transform.y - this.cell_size* this.zoom_transform.k;
                this.m.attr('transform', mat_tr);

                // SPECIES TREE
                var sp_tree_offset_y = this.grid.y_offset_st*this.zoom_transform.k - this.zoom_transform.x + (this.cell_size/2)*this.zoom_transform.k
                var x_offset_sp =  this.grid.species_tree_width_raw*this.zoom_transform.k - (this.species_tree_width)
                this.tree_target.attr('transform', 'rotate(90) translate(' + -x_offset_sp + ','+sp_tree_offset_y+ ') scale(' + this.zoom_transform.k + ')' );

                // SPECIES TREE NAME
                var offset_x = this.grid.species_tree_height_raw*this.zoom_transform.k + this.zoom_transform.x
                var offset_y =  this.grid.y_offset_st*this.zoom_transform.k + this.zoom_transform.x
                this.colName.attr('transform', `rotate(90) translate(${0}, ${-offset_x}) scale(${this.zoom_transform.k})` );
                this.colName.selectAll("text").attr('font-size', 10/this.zoom_transform.k + 'px')

                //GENE TREE
                this._zoom_update_gene_tree();

                // GENE TREE NAME
                this._zoom_update_gene_name();

                // GENE TREE LABEL
                this._zoom_update_gene_label()

                this.old_transform = this.zoom_transform;



            })

        this.SVG.call(this.zoom)

    }

    _zoom_update_gene_tree(){

        var x_offset_gt = this.grid.genes_tree_width_raw*this.zoom_transform.k - (this.genes_tree_width) + this.gene_tree_x_translate
        var y_offset_gt = (this.cell_size/2 + this.grid.y_offset_gt)*this.zoom_transform.k + this.zoom_transform.y
        this.gene_target.attr('transform', 'translate(' + -x_offset_gt + ',' +  y_offset_gt + ') scale(' + this.zoom_transform.k + ')' );

        //this.gene_target.selectAll("circle").attr('r', d => d.children || d._children ? 4/this.zoom_transform.k : 8)

    }

    _zoom_update_gene_name(scroll_mode){


            this.rowName.attr('transform', 'translate(0,' + this.zoom_transform.y + ') scale(' + this.zoom_transform.k + ')' );

            this.rowName.selectAll("text")
                .attr('font-size', (d,i) => { return i % this.sub_sampling_ratio === 0? this.leaf_font_size/this.zoom_transform.k + 'px' : 0  }  )
                .attr('x', this.gene_name_padding_left/this.zoom_transform.k + 'px')
                //.attr("y", (d, i) => { return (i + 1) * this.cell_size   })

    }


    _zoom_update_gene_label(){

        this.rowLabels.attr('transform', 'translate(0,' + this.zoom_transform.y + ') scale(' + this.zoom_transform.k + ')' );

        this.rowLabels.selectAll("text")
                .attr('font-size', (d,i) => { return i % this.sub_sampling_ratio === 0? this.leaf_font_size/this.zoom_transform.k + 'px' : 0  }  )
                .attr('x', this.gene_name_padding_left/this.zoom_transform.k + 'px')

    }

    _build_matrix(){

        this.cols = this.hierarchy_species.leaves().reverse()
        this.rows = this.hierarchy_genes.leaves()

        this.color_scale = {};

        for (var h = 0; h < this.cols.length; h++) {
            this.cols[h].empty= true

            if (this.cols[h].data.matrix_color){
                this.color_scale[this.cols[h].data.matrix_color] = null
            }
        }


        var values = [];
        var data_matrix = [];
        var max = 1



        for (var r = 0; r < this.rows.length; r++) {

            let row_profile = (this.rows[r]._children || this.rows[r].children) ? this.rows[r].profile : this.rows[r].data.profile
            for (var c = 0; c < this.cols.length; c++) {

                let val = null
                let cpt = 0

                if (this.cols[c]._children || this.cols[c].children) {

                    var collapse_cols = this.dft(this.cols[c])


                    for (var j = 0; j < collapse_cols.length; j++) {

                        var v = row_profile[collapse_cols[j].data.taxon]

                        if (v || parseInt(v)==0){
                            if (val==null){val = 0}
                            val += parseInt(v)
                            cpt  +=1
                        }


                    }

                   if (val!=null){

                    val = val/cpt

                    val = val % 1 === 0 ? val : val.toFixed(1)

                    }


                }

                else {
                    val = row_profile[this.cols[c].data.taxon]
                }

                if (val!=null) {
                    max = val > max ?  val : max
                    var color = this.cols[c].data.matrix_color ? this.cols[c].data.matrix_color : this.color_cell_default;
                    data_matrix.push({row: r + 1, col: c + 1, value: val, c: color, hog_id: this.rows[r].data.HOG, taxon_name: this.cols[c].data.taxon});
                    //data_matrix.push({row: r + 1, col: c + 1, value: val, c: color, hog_id: this.rows[r].data.HOG, taxon_name: this.cols[c].data.taxon});
                    values.push(parseFloat(val));

                    val > 0 ? this.cols[c].empty = false : null
                }
            }



        }


        const median = arr => {
            let middle = Math.floor(arr.length / 2);
            arr = [...arr].sort((a, b) => a - b);
            return arr.length % 2 !== 0 ? arr[middle] : (arr[middle - 1] + arr[middle]) / 2;
        };


        var med = median(values.filter(x => x !== 0))

        if (max < 3*med){


            for (var key in this.color_scale) {

                var color = d3.color(key);

                this.color_scale[key] = d3.scaleLinear()
                    .domain([0, 0.000000000001, 1, max])
                    .range([this.color_cell_zero, color.darker(-2), color.darker(-1), color]);
            }

            this.color_scale[this.color_cell_default] = d3.scaleLinear()
                .domain([0, 0.000000000001, 1, max])
                .range([this.color_cell_zero,'lightsalmon', 'salmon', 'red']);
        }

        else{


            for (var key in this.color_scale) {

                var color = d3.color(key);

                this.color_scale[key] = d3.scaleLinear()
                    .domain([0, 0.000000000001,1, 3*med,max])
                    .range([this.color_cell_zero, color.darker(-2), color.darker(-1), color, color.darker()]);
            }

            this.color_scale[this.color_cell_default] = d3.scaleLinear()
                .domain([0, 0.000000000001,1, 3*med,max])
                .range([this.color_cell_zero,'lightsalmon', 'salmon', 'red',  'brown']);

        }

        this.scaleText = d3.scaleLinear()
            .domain([0, 0.000000000001, max])
            .range(['black', 'white','white']);


        this.hierarchy_species.eachAfter((d) => {
            if (d.children) {

                 d.children.every( e  => e.empty == true) ? d.empty = true : d.empty = false

                }
        })

        this.data_matrix = data_matrix;

    }

    _zoom_start() { // initial zoom

        var t = d3.zoomIdentity.translate(0, 0).scale(this.ratio_zoom);

        this.SVG.call(this.zoom.transform, t)

    }

    _zoom_ping() { // initial zoom

        var t = d3.zoomTransform(this.SVG.node());

        this.SVG.call(this.zoom.transform, t)

    }

    _render_species_tree(){


          // Add a clipPath: everything out of this area won't be drawn.
      var clip2 = this.SVG.append("defs").append("SVG:clipPath")
          .attr("id", "clip2")
          .append("SVG:rect")
          .attr("width", this.grid.board_width )
          .attr("height", this.species_tree_width )
          .attr("x", 0)
          .attr("y", 0);

        this.g_stg = this.G.append('g').attr('id', 'g_species').
                attr("transform", `translate(${this.grid.startx_st}, ${this.grid.starty_st})`)
        .attr("clip-path", "url(#clip2)")

        this.tree_target =  this.g_stg.append('g')
             .attr('width',  this.species_tree_width)
            .attr("x", 0)
          .attr("y", 0)

        this.root_species = d3.cluster()

            .nodeSize([this.cell_size, (this.species_tree_width/this.ratio_zoom) / (this.hierarchy_genes.height + 1)])
            .separation(() =>  { return 1})
            (this.hierarchy_species);


        this.tree_target.selectAll("path")
            .data(this.root_species.links())
            .join("path")
            .attr("fill", "none")
            .attr("stroke", (d) => {return d.target.data.color ? d.target.data.color : "#555"})
            .attr("stroke-opacity", 0.5)
            .attr("stroke-width", (d) => {
                var w = 2 + (d.target._children ? 2*this.dft(d.target).length : 0)
                return Math.min(this.cell_size/2, w)
            })
            .attr("d", d =>{
                var s = d.target;
                var d = d.source;
                return   "M" + s.y + "," + s.x + "L" + d.y + "," + s.x + "L" + d.y + "," + d.x;})


        this.tree_target.selectAll("circle")
            .data(this.root_species.descendants())
            .join("circle")
            .attr("cx", d => d.y )
            .attr("cy", d => d.x )
            .attr("fill", d => d.children || d._children ? "#555" : "#999")
            .attr("r", 8)
            /*
            .on("mouseover", (d,i) => {this.handleMouseOver(d.target)})
            .on("mouseout", (d,i) => this.handleMouseOut(d.target))

             */



        this.tree_target.append("g")
            .selectAll(".colLabelg")
            .data(this.root_species.descendants())
            .enter()
            .append("text")
            .filter(function(d) { return d._children || d.children })
            .text(function (d) {
                if (d._children){ return "\u002B";}
                else if (d.children){ return "\u2212";}

            })
            .attr('fill', 'white')
            .attr('cursor', 'pointer')
            .attr("x", d => d.y-5)
            .attr("y", d => d.x +5)
            .style("text-anchor", "start")
            .on("click", (event, d) => {
                this.collapse(d)
                this.collapse_gene_by_species_name(d)
            })

        this.grid.y_offset_st = -this.cols[0].x
        this.grid.species_tree_width_raw = this.tree_target.node().getBoundingClientRect().width
        this.grid.species_tree_height_raw = this.tree_target.node().getBoundingClientRect().height

    }

    _render_matrix(){


        // Add a clipPath: everything out of this area won't be drawn.
      var clip = this.SVG.append("defs").append("SVG:clipPath")
          .attr("id", "clip")
          .append("SVG:rect")
          .attr("width", this.grid.board_width )
          .attr("height", this.grid.board_height )
          .attr("x", 0)
          .attr("y", 0);



        this.g_mg = this.G.append('g').attr('id', 'g_matrix').
        attr("transform", `translate(${this.grid.startx_st}, ${this.grid.starty_gt })`)
        .attr("clip-path", "url(#clip)")



         this.m = this.g_mg.append('g')
            .attr("x", 0)
            .attr("y", 0)
             .attr('width', this.grid.board_width)
                .attr('height', this.grid.board_height)


        this.m.selectAll("rect")
            .data(this.data_matrix, function (d) {
                return d.row + ":" + d.col;
            })
            .join("rect")
            .filter(d => {return d.value !== ''})
            .attr("x",  (d) => {
                return d.col * this.cell_size;
            })
            .attr("y",  (d) =>  {
                return d.row * this.cell_size;
            })
            .attr("class", function (d) {
                return "cell cell-border cr" + (d.row - 1) + " cc" + (d.col - 1);
            })
            .attr("width", this.cell_size)
            .attr("height", this.cell_size)
            .style("fill",  (d) => {
                if (d.value === "0.0") {return this.color_scale[d.c](0.0000001)}
                return this.color_scale[d.c](d.value)
            })



        var valuesText = this.m.selectAll("text")
            .data(this.data_matrix, function (d) {
                return d.row + ":" + d.col;
            })
            .join('text')
            .filter(d => {return d.value !== ''})
            .text(function (d) {
                if (d.value === "0.0") {return '>0'}
                else if (d.value >=  10){
                    return parseFloat(d.value).toFixed(0)
                }
                return d.value;
            })
            .attr("x",  (d) => {
                if (d.value.toString().includes(".")) {
                    return d.col * this.cell_size + this.cell_size/2 -10 ;
                }
                if(d.value >= 10){
                    return d.col * this.cell_size + this.cell_size/2 -9 ;
                }
                return d.col * this.cell_size + this.cell_size/2 -4 ;
            })
            .attr("y",  (d) => {
                return d.row * this.cell_size + this.cell_size/2 +4;
            })
            .style("fill",  (d) => {
                if (d.value == 0 && d.c != 'red'){
                    return d.c
                }
                if (d.value === "0.0") {return this.scaleText(0.0000001)}
                return this.scaleText(d.value)
            })



        this.m.selectAll("g")
            .data(this.data_matrix, function (d) {
                return d.row + ":" + d.col;
            })
            .join("rect")
            .filter(d => {return d.value !== ''})
            .attr("x",  (d) => {
                return d.col * this.cell_size;
            })
            .attr("y",  (d) =>  {
                return d.row * this.cell_size;
            })
            .attr("width", this.cell_size)
            .attr("height", this.cell_size)
            .style('fill', 'white')
             .attr('cursor', 'pointer')
            .attr('opacity', '0')
            .on("click", (event, node) => {

                var hid = node.hog_id.includes('HOG:') ? node.hog_id : node.HOG_name

                console.log(hid, node.taxon_name)

                //this._click_square(event, hid, node.taxon_name )

            })
            .on("mouseover", (event, d) => {

                var tr = this.zoom_transform ? this.zoom_transform : d3.zoomTransform(this.SVG.node());

                var pos_x = d.col  * this.cell_size * tr.k + tr.x
                var pos_y = d.row  * this.cell_size * tr.k + tr.y


                this.clean_crosshair()


                this.g_mg.append("line")
                    .attr("class", "vline")
                    .attr("x1", pos_x  )  //<<== change your code here
                    .attr("y1", -10000)
                    .attr("x2", pos_x  )  //<<== and here
                    .attr("y2", 10000)
                    .style("stroke-width", this.crosshair_width * tr.k)
                    .style("stroke", "grey")
                    .style("fill", "none");


                // HORYZONTAL LINE

                this.g_mg.append("line")
                    .attr("class", "hline")
                    .attr("x1", -1000)  //<<== change your code here
                    .attr("y1", pos_y  )
                    .attr("x2", 1000)  //<<== and here
                    .attr("y2", pos_y)
                    .style("stroke-width", this.crosshair_width * tr.k)
                    .style("stroke", "grey")
                    .style("fill", "none");

                this.g_gtn.append("line")
                    .attr("class", "hline_gtn")
                    .attr("x1", 0)  //<<== change your code here
                    .attr("y1", pos_y  )
                    .attr("x2", this.gene_name_width)  //<<== and here
                    .attr("y2", pos_y)
                    .style("stroke-width", this.crosshair_width * tr.k)
                    .style("stroke", "grey")
                    .style("fill", "none");

                this.g_gtl.append("line")
                    .attr("class", "hline_gtl")
                    .attr("x1", 0)  //<<== change your code here
                    .attr("y1", pos_y  )
                    .attr("x2", this.gene_label_width)  //<<== and here
                    .attr("y2", pos_y)
                    .style("stroke-width", this.crosshair_width * tr.k)
                    .style("stroke", "grey")
                    .style("fill", "none");



                /*
                this.g_mg.append("line")
                    .attr("class", "hline2")
                    .attr("x1", xy[0] + this.cell_size* this.ratio_zoom)  //<<== change your code here
                    .attr("y1", xy[1] - this.cell_size* this.ratio_zoom)
                    .attr("x2", xy[0] + this.cell_size* this.ratio_zoom)  //<<== and here
                    .attr("y2", xy[1] )
                    .style("stroke-width", 2)
                    .style("stroke", "grey")
                    .style("fill", "none");

                this.g_mg.append("line")
                    .attr("class", "vline2")
                    .attr("x1", xy[0] + this.cell_size* this.ratio_zoom)  //<<== change your code here
                    .attr("x2", xy[0]  )
                    .attr("y1", xy[1] - this.cell_size* this.ratio_zoom)
                    .attr("y2", xy[1] - this.cell_size* this.ratio_zoom)
                    .style("stroke-width", 2)
                    .style("stroke", "grey")
                    .style("fill", "none");

                 */
            })
            .on("mouseout", (event, d) => {
                 this.clean_crosshair()

            })




        this.ratio_zoom = this.grid.board_width / this.m.node().getBoundingClientRect().width;


    }

    _render_gene_tree() {

               // Add a clipPath: everything out of this area won't be drawn.
      var clip3 = this.SVG.append("defs").append("SVG:clipPath")
          .attr("id", "clip3")
          .append("SVG:rect")
          .attr("width", this.genes_tree_width )
          .attr("height", this.grid.board_height )
          .attr("x", 0)
          .attr("y", 0);

        this.g_gtg = this.G.append('g').attr('id', 'g_gene').
        attr("transform", `translate(${this.grid.startx_gt}, ${this.grid.starty_gt})`)
        .attr("clip-path", "url(#clip3)")

        this.gene_target =  this.g_gtg.append('g')
            .attr('id', 'g_gene_g')
             .attr('width',  this.genes_tree_width)
            .attr("x", 0)
          .attr("y", 0)


        this.root_genes = d3.cluster()
            .nodeSize([this.cell_size, (this.genes_tree_width/this.ratio_zoom) / (this.hierarchy_genes.height + 1)])
            .separation(() =>  { return 1})(this.hierarchy_genes);

        // annotate whole tree with placement tag
        // annotate whole tree with losses tag
        this.root_genes.eachBefore(d => {
            //if (d.data.placed) {
            //    d.descendants().forEach(element => {
            //        element.data.placed = d.data.placed
            //    });
            //}
            if (d.data.event === 'loss') {
                d.descendants().forEach(element => {
                    element.data.loss = true
                });

            }

        })


        this.gene_target.selectAll("path")
            .data(this.root_genes.links())
            .join("path")
            .attr("fill", "none")
            .attr("stroke", (d) => {return d.target.data.color ? d.target.data.color : "#555"})
            .attr("stroke-opacity", (d) => {return d.target.data.event === 'loss' || d.target.parent.data.event === 'loss'  ? 0.2 : 0.5})
            .attr("stroke-width", (d) =>{
                var w = 2 + (d.target._children ? 2*this.dft(d.target).length : 0)
                return Math.min(this.cell_size/2, w)
            })
            .attr("d", d =>{
                var s = d.target;
                var d = d.source;
                return   "M" + s.y + "," + s.x + "L" + d.y + "," + s.x + "L" + d.y + "," + d.x;
            })


        this.gene_target.selectAll("circle")
            .data(this.root_genes.descendants())
            .join("circle")
            .filter(function(d) {return d.parent })
            .attr("cx", d => d.y )
            .attr("cy", d => d.x )
            .style("cursor", "pointer")
            .attr("fill", d => d.children || d._children ? "#555" : "#999")
            .attr("r", d=>  d.parent && (d.data.event == 'hgt' || d.data.event == 'duplication' || (d.data.event == 'loss'  && d.parent.data.event != 'loss' ))  ? 1 : 8)
            .on("click", (event, d) => {

                if (d.data.event != 'loss'){
                    this.collapse(d)
                }

            })


        this.gene_target
            .selectAll(".rowLabelg")
            .data(this.root_genes.descendants())
            .join("g")
            .append("text")
            .filter(function(d) {return d.data.event == 'duplication' && d.parent })
            .text(function (d) {return "\u2731"
            })
            .attr('fill', '#555')
            .style("font-size", "40px")
            .style("cursor", "pointer")
            .attr("x", d => d.y )
            .attr("y", d => d.x + 15)
            .style("text-anchor", "middle")


        this.gene_target
            .selectAll(".rowLabelg")
            .data(this.root_genes.descendants())
            .join("g")
            .append("text")
            .filter(function(d) {return d.data.event == 'loss'  && d.parent.data.event != 'loss' })
            .text(function (d) {return "\u274C"
            })
            .attr('fill', 'black')
            .style("font-size", "20px")
            .style("cursor", "pointer")
            .attr("x", d => d.y )
            .attr("y", d => d.x + 8)
            .style("text-anchor", "middle")
            .on("click", (event, d) => {
                this.collapse( d)
            })


        this.gene_target
            .selectAll(".rowLabelg")
            .data(this.root_genes.descendants())
            .join("g")
            .append("text")
            .filter(function(d) {return d.data.event == 'hgt' })
            .text(function (d) {return "\u21DD"
            })
            .attr('fill', '#555')
            .style("font-size", "3em")
            .style("cursor", "pointer")
            .attr("x", d => d.y )
            .attr("y", d => d.x + 13)
            .style("text-anchor", "middle")


        this.gene_target.selectAll(".rowLabelg")
            .data(this.root_genes.descendants())
            .join("g")
            .append("text")
            .filter(function(d) { return (d._children || d.children) && d.data.event != 'loss' && d.parent})
            .text(function (d) {
                if (d._children){ return "\u002B";}
                else if (d.children){ return "\u2212";}

            })
            .attr('fill', 'white')
    .style("cursor", "pointer")
            .attr("x", d => d.y)
            .attr("y", d => d.x + 5)
            .style("text-anchor", "middle")
            .on("click", (event, d) => {
                this.collapse(d)
            })



        // need to update grid ofsset depending on the tree size
        this.grid.genes_tree_width_raw = this.gene_target.node().getBoundingClientRect().width
        this.grid.y_offset_gt = -this.rows[0].x


    }

    _render_genes_labels(){

        var clip5 = this.SVG.append("defs").append("SVG:clipPath")
          .attr("id", "clip5")
          .append("SVG:rect")
          .attr("width", this.gene_label_width )
          .attr("height", this.grid.board_height )
          .attr("x", 0)
          .attr("y", 0);

        this.g_gtl = this.G.append('g').attr('id', 'g_genes_labels').
        attr("transform", `translate(${this.grid.startx_glabel}, ${this.grid.starty_gt})`)
        .attr("clip-path", "url(#clip5)")

        this.rowLabels =  this.g_gtl.append('g')
             .attr('width',  this.genes_tree_width)
            .attr("x", 0)
          .attr("y", 0)

         this.rowLabels.selectAll(".rowLabelg")
            .data(this.hierarchy_genes.leaves())
            .enter()
            .append("text")
            .attr("font-weight", (d) => {return d._children ? 700 : 300})
            .text( (d) => { //d.name or aggregate leaves name

                return d.data.description;
            })

            .attr("x", 0)
            .attr("y", (d, i) => {
                return (i + 1) * this.cell_size -14;
            })
            .style("text-anchor", "start")



    }

    _render_genes_names() {

        var set_name = function (d) {

            if (d.parent.parent == null){
                return d.data.HOG_name;
            }

            if (d.parent && (d.data.event == 'loss' || d.parent.data.event == "loss")) {
                return d.data.taxon
            }
            if (d._children && d.data.event !== 'loss') {
                if (d.data.HOG) {
                    return d.data.HOG
                }
                var name = ""
                this.dft(d).forEach(function (d) {
                    name += d.data.gene
                })
                return name

            }
            return d.data.gene;
        }


        var clip4 = this.SVG.append("defs").append("SVG:clipPath")
          .attr("id", "clip4")
          .append("SVG:rect")
          .attr("width", this.gene_name_width )
          .attr("height", this.grid.board_height )
          .attr("x", 0)
          .attr("y", 0);

        this.g_gtn = this.G.append('g').attr('id', 'g_genes_names').
        attr("transform", `translate(${this.grid.startx_gt + this.genes_tree_width}, ${this.grid.starty_gt})`)
        .attr("clip-path", "url(#clip4)")

        this.rowName =  this.g_gtn.append('g')
             .attr('width',  this.genes_tree_width)
            .attr("x", 0)
          .attr("y", 0)

        this.rowName.selectAll(".rownameg")
            .data(this.hierarchy_genes.leaves())
            .enter()
            .append("text")
            .attr("font-weight", (d) => {
                return d._children  ? 700 : 300
            })
            .style("fill", (d) => {
                if(d.parent){
                    return d.parent.data.event == "loss" || d.data.event == "loss"  ? 'lightgrey'  : 'black';
                }
                else {

                    return 'black';
                }
            })
            .text((d) => {
                return set_name(d)
            })
            .attr("x", this.gene_name_padding_left)
            .attr("y", (d, i) => { return (i + 1) * this.cell_size - this.gene_name_padding_y;
            })
            .style("text-anchor", "start")

            .each((d, i, nodes) => {
                this.wrap(nodes[i], this.gene_name_width)
            })
        .on("mouseover", (event, d) => {
            event.target.innerHTML = set_name(d)
        })
        .on("mouseout", (event) => {
            this.wrap(event.target, this.gene_name_width)
        })


    }

    _render_species_names(){

         this.SVG.append("defs").append("SVG:clipPath")
          .attr("id", "clip6")
          .append("SVG:rect")
          .attr("width", this.grid.board_width )
          .attr("height", this.species_name_width )
          .attr("x", 0)
          .attr("y", 0);

        this.g_stn = this.G.append('g').attr('id', 'g_species_name').
       attr("transform", `translate(${this.grid.startx_st}, ${this.grid.starty_st + this.species_tree_width})`)
        .attr("clip-path", "url(#clip6)")

        this.colName =  this.g_stn.append('g')
             .attr('width',  this.genes_tree_width)
             .attr('height', this.species_name_width)
            .attr("x", 0)
          .attr("y", 0)

        this.colName.selectAll(".colnameg")
            .data(this.hierarchy_species.leaves())
            .enter()
            .append("text")
            .style("fill", (d) => {
                if(d.data.matrix_color){
                  return d.data.matrix_color
                }
                else {

                    return 'black';
                }
            })
            .attr("font-weight", (d) => {return d._children ? 700 : 300})
            .text(function (d) {
                return d.data.taxon;
            })
            .attr("x", 0)
            .attr("y",  (d, i) => {
                return (i + 1) * this.cell_size;
            })
            .style("text-anchor", "start")
            .each((d,i,nodes) => this.wrap(nodes[i],this.species_name_width))
            /*
            .on("mouseover", (event, d) => {
                if (this.show_image){ (async() => {

        const endpoint = encodeURI('http://en.wikipedia.org/w/api.php?action=query&titles=' + d.data.taxon +'&prop=pageimages&origin=*&format=json&pithumbsize=200');
        const img = await d3.json(endpoint, {crossOrigin: "anonymous"});

        var idimg,j= null;
        j = JSON.parse(JSON.stringify(img.query.pages))
        for (var k in j ) { idimg = k; break;}


        try {
            j[idimg].thumbnail.source
        }
        catch (e) {
            return
        }


        div.html('')



        div.transition()
            .duration(200)
            .style("opacity", 1);

        div.html("<b>" + d.data.taxon + "</b>" )
            .style("left", (event.pageX) + "px")
            .style("top", (event.pageY - 28) + "px");



        div.html("<b>" + d.data.taxon + "</b>" + '<img src="' + j[idimg].thumbnail.source + '">')
            .style("left", (event.pageX) + "px")
            .style("top", (event.pageY - 28) + "px");






    })();
                event.target.innerHTML = d.data.taxon}
            })
            .on("mouseout", (event) => {
                this.wrap(event.target, this.gene_name_width)
                div.transition()
                    .duration(250)
                    .style("opacity", 0);
            })

             */



    }













    clean_crosshair(){

           d3.select('.vline').remove()
            d3.select('.vline2').remove()


            d3.select('.hline').remove()
            d3.select('.hline2').remove()
            d3.select('.hline_gtn').remove()
            d3.select('.hline_gtl').remove()
    }

    augment_species_tree(mapping){

        function traverse(o) {

            if ('name' in o && o['name']  in mapping){

                var e = mapping[o['name']];

                for (const eKey in e) {
                    o[eKey] = e[eKey]

                }
            }

            for (var i in o) {

                if (!!o[i] && typeof(o[i])=="object") {

                    traverse(o[i]);
                }
            }
        }

        traverse(this.data_species_tree)

    }

    add_tree(tree){

        var tree_filtered = this.remove_single_level(tree);

        this.data_gene_tree_list.push(tree_filtered)
        this.build_data_gene_tree()
    }

    remove_single_level(o) {

        if(o["children"]){

            var to_remove = [];

            for (var c in o["children"] ) {

                var child = o["children"][c]

                child = this.remove_single_level(child)

                if (child["children"] && child["children"].length == 1){

                    to_remove.push(child);

                }

        }

            for (const toRemoveKey in to_remove) {

                var tr = to_remove[toRemoveKey];

                 o["children"].push(tr["children"][0])

                    var index = o["children"].indexOf(tr);
                    if (index > -1) {
                        o["children"].splice(index, 1);
                    }

            }

            }

        return o

    }

    build_data_gene_tree() { // TODO

        this.data_gene_tree = {
            "HOG": "ROOT",
            "taxon": "Vertebrata",
            "event": "duplication",
            "description": "Vertebrata",
            "children": this.data_gene_tree_list
        }

    }

    //



    add_legend(){




        this.SVG.append("text")
            .text(function (d) {return "\u2731"
            })
            .attr('fill', '#555')
            .style("font-size", "25px")
            .attr('x', this.gutter)
            .attr('y', this.gutter + 20)
            .style("text-anchor", "start")




        this.SVG.append('text')
            .attr('x',  this.gutter + 20 + 8)
            .attr('y', this.gutter + 20 - 4 )
            .text('Duplication')



        this.SVG.append("text")
            .text(function (d) {return "\u274C"
            })
            .attr('fill', '#555')
            .style("font-size", "18px")
            .attr('x', this.gutter)
            .attr('y', 2*this.gutter + 38)
            .style("text-anchor", "start")

        this.SVG.append('text')
            .attr('x',  this.gutter + 20 + 8)
            .attr('y', 2*this.gutter + 40 - 4 )
            .text('Loss')


        this.SVG.append("text")
            .text(function (d) {return "\u21DD"
            })
            .attr('fill', '#555')
            .style("font-size", "32px")
            .attr('x', this.gutter)
            .attr('y', 3*this.gutter + 60)
            .style("text-anchor", "start")

        this.SVG.append('text')
            .attr('x',  this.gutter + 20 + 8)
            .attr('y', 3 * this.gutter + 60 - 4 )
            .text('HGT')


    }


    //

    render_species_labels(){

        function hasUnicode (str) {
            for (var i = 0; i < str.length; i++) {
                if (str.charCodeAt(i) > 127) return true;
            }
            return false;
        }


        this.colLabels.selectAll(".colLabelg")
            .data(this.hierarchy_species.leaves())
            .enter()
            .append("text")
            .attr("font-weight", (d) => {return d._children ? 700 : 300})
            .text((d)  => {
                return d.data.description;
            })
            .style("fill", (d) => {return this.speciesColor(d.data.description)})
            .attr("x", 0)
            .attr("y",  (d, i) => {
                return (i + 1) * this.cell_size;
            })
            .style("text-anchor", "start")
            .attr("transform", (d, i) => {
                if (hasUnicode(d.data.description) ) {
                    return "translate(" + ((i +0.5) * -this.cell_size) +"," + ((i + 1) * this.cell_size) +") rotate(-90)";
                }
                return "rotate(0)";
            } )

    }

    collapse(d ){
        if (d.children) {
            d._children = d.children;
            d.children = null;
        }
        else {
            d.children = d._children;
            d._children = null;


        }

        if (d.data.HOG){this.update_profile_to_collapse_node(d)}
        this.data_matrix = this._build_matrix()

        this._render()
        this._zoom_ping()
        //this.recalibrate_position()


    }

    collapse_gene_by_species_name(d, render_loop=true){

        var hog  = []
        var stack=[];
        stack.push(this.hierarchy_genes);
        while(stack.length!==0){
            var element = stack.pop();
            if ( element.data.taxon === d.data.taxon && element.data.event === "speciation" ){
                hog.push(element)
            }

            if(element.children != null){
                for(let i=0; i<element.children.length; i++){
                    var c = element.children[element.children.length-i-1]
                    stack.push(c)
                }
            }
            else if(element._children != null){
                for(let i=0; i<element._children.length; i++){
                    var c = element._children[element._children.length-i-1]
                    stack.push(c)

                }
            }

        }


        var to_collapse = d.children ? false : true

        hog.forEach(e => {


            if (to_collapse) {
                if (e._children) {if (e.data.HOG){this.update_profile_to_collapse_node(e)};return}
                e._children = e.children;
                e.children = null;

            }
            else {
                if (e.children) {if (e.data.HOG){this.update_profile_to_collapse_node(e)};return}
                e.children = e._children;
                e._children = null;
            }

            if (e.data.HOG){this.update_profile_to_collapse_node(e)}


        })

        if(render_loop){this.data_matrix = this._build_matrix()

            this._render()

            //this.recalibrate_position()
             }



}

    update_profile_to_collapse_node(d){

        if (d.children) {
            d.profile = null;
        }
        else {
            d.profile = new defaultDict();

            var collapsed_rows = this.dft(d)

            for (var c = 0; c < collapsed_rows.length; c++) {

                var p = collapsed_rows[c].data.profile

                for (var [key, value] of Object.entries(p)) {

                    if (value){
                        d.profile[key] = d.profile.get(key) + parseInt(value);}
                }

            }

        }
    }

    wrap(node, size) {


        var self = d3.select(node),text = self.text();

        var l = Math.floor(this.gene_name_width/10)

        if (text.length > l){
            text = text.slice(0,l)
            self.text(text + '...');
        }


        /*
        var self = d3.select(node),
            textLength = self.node().getComputedTextLength(),
            text = self.text();
        while (textLength > (size-10) && text.length > 0) {
            text = text.slice(0, -8);
            self.text(text + '...');
            textLength = self.node().getComputedTextLength();
        }

         */
    }

    handleMouseOver(d){
        d3.select(d).attr('fill', "green")
    }

    handleMouseOut(d){
        d3.select(d).attr('fill', this.node_color)
    }

    //
    dft(root){
        var leaves = []
        var stack=[];
        stack.push(root);
        while(stack.length!==0){
            var element = stack.pop();
            if(element.children != null){
                for(let i=0; i<element.children.length; i++){
                    var c = element.children[element.children.length-i-1]
                    stack.push(c)
                }
            }
            else if(element._children != null){
                for(let i=0; i<element._children.length; i++){
                    var c = element._children[element._children.length-i-1]
                    stack.push(c)

                }
            }
            else{leaves.push(element)}
        }
        return leaves
    }

    expandAll(){

        this.root_species.each(d => {
            if (d._children) {
                d.children = d._children;
                d._children = null;
            }
        })

        this.root_genes.each(d => {
            if (d._children && d.data.event != 'loss') {
                d.children = d._children;
                d._children = null;
            }
        })


    }

    start_collapse(){

        // All collapse at start (one row) inside subtree with no hgt/duplication are fully collapsed and duplicated node are collapse
        //species specific duplication are collapse at the duplication node


        this.root_species.each(d => {

            if (d.children && (d.empty === true || this.start_collapse_depth <= d.depth)){
                if (d.children) {
                    d._children = d.children;
                    d.children = null;
                }
                else {
                    d.children = d._children;
                    d._children = null;
                }
                this.collapse_gene_by_species_name(d, false)

            }
        })


        this.root_genes.eachAfter(d => {


            if (d.data.event === 'duplication' || d.data.event === 'hgt' ) {


                if (d.data.event === 'duplication' && d.children) {

                    var all_extant_species = true

                    d.children.forEach(c => {
                        if (c.children != null || c._children != null) {
                            all_extant_species = false
                        }
                    })

                    if (!all_extant_species) {
                        d.has_event = true

                        d.ancestors().forEach(element => {
                            element.has_event = true
                        });
                    }
                }

                else {
                    d.has_event = true

                    d.ancestors().forEach(element => {
                    element.has_event = true
                    });
                }

            }

            else {

                if (d.has_event != true){
                    d.has_event = false}
                }

        })

        this.root_genes.eachAfter(d => {



            if ((d.data.event == 'loss' || !d.has_event) && d.children ){
                d._children = d.children;
                d.children = null;
            }


            if (d.parent == null && d.children ) {

                if (d.data.event != "duplication"){
                    d._children = d.children;
                    d.children = null;
                }
            }

            else {
                if (d.children && d.parent.data.event == "duplication") {
                    d._children = d.children;
                    d.children = null;
                }

                if (d.data.event == "duplication") {

                    if (d.children){
                        var all_extant_species = true

                        d.children.forEach(c => {
                            if (c.children != null || c._children != null ) {
                                all_extant_species= false
                            }
                        } )

                        if (all_extant_species){
                            d._children = d.children;
                            d.children = null;
                        }
                    }



                }
            }





            if (d.data.HOG){this.update_profile_to_collapse_node(d)}

        })

        this.data_matrix = this._build_matrix()
        this._render()
        //this.recalibrate_position()


    }

    smart_collapse(){

        this.root_species.each(d => {
                if (d.children && (d.empty === true || this.start_collapse_depth <= d.depth)){
                    if (d.children) {
                        d._children = d.children;
                        d.children = null;
                    }
                    else {
                        d.children = d._children;
                        d._children = null;


                    }
                    this.collapse_gene_by_species_name(d, false)

                }
            })

        this.root_genes.eachAfter(d => {


            if (d.data.event === 'duplication') {

                if (d.children){
                    var all_extant_species = true

                    d.children.forEach(c => {
                        if (c.children != null || c._children != null ) {
                            all_extant_species= false
                        }
                    } )

                    if (!all_extant_species){
                        d.dontcol = true

                        d.ancestors().forEach(element => {
                            element.dontcol= true
                        })
                    }
                }




            }

        })

        this.root_genes.eachAfter(d => {


            if (d.dontcol !== true || d.data.event === 'loss') {

                if (d.children) {
                    d._children = d.children;
                    d.children = null;
                }


                if (d.data.HOG){this.update_profile_to_collapse_node(d)}
            }

            if (d.data.event == "duplication") {

                if (d.children){
                    var all_extant_species = true

                    d.children.forEach(c => {
                        if (c.children != null || c._children != null ) {
                            all_extant_species= false
                        }
                    } )

                    if (all_extant_species){
                        d._children = d.children;
                        d.children = null;
                    }
                }



            }

            })

        this.data_matrix = this._build_matrix()
        this._render()
    }

    update_svg_size_responsive(){
        this.container_size = this.d3_container.node().getBoundingClientRect();
        this.start();
    }

     render_tooltip(x, y, menu) {

         d3.select(".tooltip").remove()

         this.Tooltip = this.d3_container.append("div") //this.d3_container.append("div")
            .style("opacity", 0)
            .attr("class", "tooltip")
            .style("background-color", "white")
            .style("border", "solid")
            .style("border-width", "1px")
            .style("border-radius", "4px")
            .style("padding", "8px")
            .style("position", "absolute")
            .style("font-size", '16px')
            .style("z-index", '900')


        this.Tooltip.style("opacity", 1).style("display", 'block')
            .style("left", x + 12 + "px")
            .style("top", y + 12 + "px")

        this.Tooltip.html('')

        var gg = this.Tooltip.selectAll('menu_item')
            .data(menu)
            .enter().append('text')
            .style('text-align', 'center')
            .style('display', 'block')
            .style('cursor', (d) => {
                return d.action ? 'pointer' : 'auto'
            })
            .style("font-weight", (d,i) => {return i == 0 || d.title === "Close" ? 900 : 400 })
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

    _click_square(event, data, level) {


         var menu = [];

         var t = {title: data, action: () => {
                                this.call_back_hog_detail( data,level)
                            } }
        menu.push(t)


         var tt = {title: '( ' + level +  ' )', action: null}
        menu.push(tt)



        var close = {
            title: 'Close',
            action: () => {
                this.close_tooltip()
            }
        }

        menu.push(close)

        this.render_tooltip(event.pageX + 12, event.pageY + 12, menu)

            }

    close_tooltip() {
        this.Tooltip.style("opacity", 0).style("display", 'none')
    }

    call_back_hog_detail(hog,level){

    }

}

