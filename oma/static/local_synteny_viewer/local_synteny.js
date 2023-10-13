class LocalSyntenyViewer {

    constructor(div_id, reference_element, hog_tree, focus, species, call_back_hog_detail, call_back_hog_local_synteny, callback_gene_local_synteny, call_back_gene_detail) {

        var that = this // ugly handle for non-arrow function usage

        // MODEL
        this.hog_tree = hog_tree
        this.reference_element = reference_element
        this.focal_hog = focus
        this.focal_species = species
        this.data = d3.hierarchy(this.find_focal_root());
        this.synteny_data = {}
        this.domain_scale = null

        //VIEWER
        this.div_id = div_id;
        this.div = d3.select("#" + this.div_id);

        // CONTROLLER
        this.settings = {
            //Data
            hald_window: 5,
            // UI GENERAL
            marginTop: 80,
            marginRight: 20,
            marginBottom: 40,
            marginLeft: 40,
            width_board: document.getElementById(this.div_id).offsetWidth,
            width_tree: 200,
            width_text: 200,
            // UI TREE
            dx: 40,
            circle_radius: 4,
            circle_radius_leaf: 3,
            length_displayed_name_leaf: 20,
            length_displayed_name_leaf_sub: 20,
            textMarginRight: 10,
            // UI SYNTENY
            height_synteny: 20,
            ref_synteny_bottomMargin: 30,
            blockMargin: 6,
            marginLeftSynteny: 20,
            color_scheme: ['#9e0142', '#d53e4f', 'salmon', '#f46d43', '#fdae61', '#fee08b', '#e6f598', '#abdda4', '#66c2a5', '#3288bd', '#5e4fa2'],
            first_render:true,
            max_leaves_shown_init: 30,
        }
        this.call_back_hog_detail = call_back_hog_detail
        this.call_back_hog_local_synteny = call_back_hog_local_synteny
        this.callback_gene_local_synteny = callback_gene_local_synteny
        this.call_back_gene_detail = call_back_gene_detail

        this.settings['width_block'] = -6 + (document.getElementById(this.div_id).offsetWidth - this.settings['width_tree'] - this.settings['marginLeftSynteny'] - this.settings['width_text']) / (1 + 2 * (this.settings['hald_window']))

        // LOAD THE FOCAL HOG SYNTENY

         var level_query = this.focal_hog !== this.reference_element ? '' :  '&level=' + this.focal_species;

        $.ajax({
            url: "/api/synteny/" + that.reference_element + "/?evidence=linearized&context=" + that.settings.hald_window + level_query,
            dataType: 'json',
            async: false,
            success: function (jsonData) {

                that.load_and_process_synteny_api(that.reference_element, jsonData, true, level_query.replace('&level=', ''))

                that.domain_scale =  that.synteny_data[that.reference_element + level_query.replace('&level=', '')].linear_synteny.map(hog => that.get_hog_id(hog))

                that.color_scale = d3.scaleOrdinal().domain(that.domain_scale).range(that.settings['color_scheme'].splice(that.synteny_data[that.reference_element + level_query.replace('&level=', '')].linear_synteny.length - that.domain_scale.length)).unknown("lightgrey");

            }
        });

        if (!this.synteny_data[this.reference_element + level_query.replace('&level=', '')]) {
            this.div.append("p").text('Ancestral Synteny for ' + this.reference_element +' around '+ this.focal_species +' not found.')
                .style('text-align', 'center')
                .style('top', '200px')
                .style('position', 'relative')
            return
        }

        // Create the SVG container, a layer for the links and a layer for the nodes.
        this.svg = this.div.append("svg")
            .attr("width", this.settings.width)
            .attr("height", this.settings.dx)
            .attr("viewBox", [-this.settings.marginLeft, -this.settings.marginTop, this.settings.width_board, this.settings.dx])
            .attr("style", "max-width: 100%; height: auto; font: 10px sans-serif; user-select: none;")

        this.gLink = this.svg.append("g")
            .attr("fill", "none")
            .attr("stroke", "#555")
            .attr("stroke-opacity", 0.4)
            .attr("stroke-width", 1.5);

        this.gNode = this.svg.append("g")
            .attr("cursor", "pointer")
            .attr("pointer-events", "all");

        this.Tooltip = this.div.append("div")
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

        // init the d3 tree model
        this.root = d3.hierarchy(this.data);

        // Apply the d3 layout to the model
        this.settings['dy'] = (this.settings.width_tree - this.settings.marginRight - this.settings.marginLeft) / (1 + this.root.height)
        this.tree = d3.cluster()
            .nodeSize([this.settings.dx, this.settings.dy])
            .separation(function (a, b) {
                return 1;
            })

        // Build and init the tree viewer instance
        this.tree(this.root);
        this.root.x0 = this.settings.dy / 2;
        this.root.y0 = 0;

        var init_depth_collapse = this.get_init_collapse()

        this.root.descendants().forEach((d, i) => {
            d.id = i;

            if (d.depth >= init_depth_collapse && !d.data.data.paralog) {
                d._children = d.children;
                d.children = null;
            }


        });

        // First rendering
        this.update(null, this.root);

    }

    // VIEWER

    get_init_collapse(){

        var depth;
        for (depth = 1; depth < this.root.height; depth++) {

            var X = this.get_number_visible_tree_tips_at_depth(depth)

            if (X > this.settings.max_leaves_shown_init) {
                break
            }
        }

        return depth
    }

    get_number_visible_tree_tips_at_depth(depth){

        var tips = 0;

        this._traverse(this.root, function(node,children){

            if (node.depth <= depth && !node.data.data.paralog) {tips += 1}
        })

        return tips

    }

    update(event, source) {

        var that = this // UGLY HANDLE

        d3.selectAll(".g_synteny").remove();
        d3.selectAll(".g_legend").remove();
        this.close_tooltip()

        const duration = event?.altKey ? 2500 : 250; // hold the alt key to slow down the transition
        const nodes = this.root.descendants().reverse();
        const links = this.root.links();

        // Compute the new tree layout.
        this.tree(this.root);

        // Align collapse with leaves
        this.root.eachBefore(node => {
            if (node.height === 0 || node._children) {
                node.y = this.settings.width_tree - this.settings.marginLeft
            }
        });

        // Compute height of the tree
        let left = this.root;
        let right = this.root;
        this.root.eachBefore(node => {
            if (node.x < left.x) left = node;
            if (node.x > right.x) right = node;
        });
        const height = right.x - left.x + this.settings.marginTop + this.settings.marginBottom;


        // Render the reference synteny
        d3.select("#ref_line").remove();
        var x_ref = this.settings.width_tree - this.settings.marginLeft
        var y_ref = left.x - this.settings.height_synteny - this.settings.ref_synteny_bottomMargin
        var ref_synteny_g = this.svg.append('g').attr('id', 'ref_line')
            .attr("transform", () => {
                return "translate(" + x_ref + ", " + y_ref + ")"
            })

        var level_ = this.focal_hog !== this.reference_element ? '' :  this.focal_species;
        this.render_synteny(ref_synteny_g, this.synteny_data[this.reference_element + level_].linear_synteny, level_, this.reference_element )

        /*ref_synteny_g.append('text')
            .attr("dy", "0.31em")
            .attr("x", this.settings.width_text)
            .attr("text-anchor", "end")
            .text(d => this.reference_element)
            .style('font-size', "14px")
            .style("font-weight", 900)
            .style('font-family', 'monospace')

         */

        // ADD ROOT LEVEL
        this.svg.append('text')
            .attr("x",8)
            .attr("y",-14)
            .attr("text-anchor", "middle")
            .text(d => this.focal_species)
            .style('font-size', "16px")
            .style("font-weight", 900)
            .style('font-family', 'monospace')
        .attr("transform", () => {
                return "rotate(-90)"
            })


        // ADD LEGEND
        var g_legend = this.svg.append("g")
            .attr('class', 'g_legend')
            .attr("transform", () => {
                return "translate(" + -8 + ", " + y_ref + ")"
            })

        g_legend.append("circle")
            .attr("r", this.settings.circle_radius )
            .attr("fill",  'salmon' )
            .attr("stroke-width", 10)

        g_legend.append('text')
            .attr("dy", "0.31em")
            .attr("x", 10)
            .attr("text-anchor", "start")
            .text(d => 'Duplication')
            .style('font-size', "14px")
            .style('font-family', 'monospace')

        var g_legend_spe = this.svg.append("g")
            .attr('class', 'g_legend')
            .attr("transform", () => {
                return "translate(" + -8 + ", " + (y_ref + 16) + ")"
            })

        g_legend_spe.append("circle")
            .attr("r", this.settings.circle_radius )
            .attr("fill",  '#555' )
            .attr("stroke-width", 10)

        g_legend_spe.append('text')
            .attr("dy", "0.31em")
            .attr("x", 10)
            .attr("text-anchor", "start")
            .text(d => 'Speciation')
            .style('font-size', "14px")
            .style('font-family', 'monospace')


        const transition = this.svg.transition()
            .duration(duration)
            .attr("height", height)
            .attr("viewBox", [-this.settings.marginLeft, left.x - this.settings.marginTop, this.settings.width_board, height])
            .tween("resize", window.ResizeObserver ? null : () => () => this.svg.dispatch("toggle"));

        // Update the nodes…
        const node = this.gNode.selectAll("g")
            .data(nodes, d => d.id);

        // Enter any new nodes at the parent's previous position.
        const nodeEnter = node.enter().append("g")
            .attr("transform", d => `translate(${source.y0},${source.x0})`)
            .attr("fill-opacity", 0)
            .attr("stroke-opacity", 0)

        nodeEnter.append("path")
            .attr("d", d3.symbol().type(d3.symbolTriangle).size(100))
            .attr("fill", "#555")
            .attr("fill-opacity", 0)
            .attr("transform", `rotate(-90)`)

        nodeEnter.append("circle")
            .attr("r", d => d.children ? this.settings.circle_radius : this.settings.circle_radius_leaf) // TODO REMOVE THIS BUG d.children && d.children.length === 1 ? 0 :
            .attr("fill", d => d.data.data.paralog ? 'salmon' : d._children || d.children ? "#555" : "#999")
            .attr("stroke-width", 10)
            .on("click", (event, node) => { this._click_node(event,node, node.data.data.species)})


        nodeEnter.append("text")
            .attr('class', 'leaf_label')
            .attr("dy", "0.31em")
            .attr("x", this.settings.textMarginRight)
            .attr("text-anchor", "start")
            .text(d => {return this.format_sub_name(d)})
            .style('font-size', "10px")
            .style('font-family', 'monospace')
            .on("click", (event, node) => { this._click_node(event,node, node.data.data.species)})
            .clone(true).lower()
            .attr("stroke-linejoin", "round")
            .attr("stroke-width", 3)
            .attr("stroke", "white")


        /*
         nodeEnter.append("text")
            .attr('class', 'leaf_sub_label')
            .attr("dy", "14px")
            .attr("x", "14px" )
            .attr("text-anchor", "start")
            .text(d => {return this.format_sub_name(d)})
            .style('font-size', "10px")
            .style('font-family', 'monospace')
        .on("click", (event, node) => { this._click_node(event,node)})

         */


        // Transition nodes to their new position.
        const nodeUpdate = node.merge(nodeEnter)

        nodeUpdate.transition(transition)
            .attr("transform", d => `translate(${d.y},${d.x})`)
            .attr("fill-opacity", 1)
            .attr("stroke-opacity", 1)

        nodeUpdate.selectAll('.leaf_label').style('font-size', d => {
            return d._children || d.height == 0 ? '14px' : '0px'
        })

        /*
        nodeUpdate.selectAll('.leaf_sub_label').style('font-size', d => {
            return d._children || d.height == 0 ? '10px' : '0px'
        })

         */

        nodeUpdate.selectAll('path').attr("fill-opacity", d => {
            return d._children ? '1' : '0'
        })

        // Transition exiting nodes to the parent's new position.
        const nodeExit = node.exit().transition(transition).remove()
            .attr("transform", d => `translate(${source.y},${source.x})`)
            .attr("fill-opacity", 0)
            .attr("stroke-opacity", 0);

        // Update the links…
        const link = this.gLink.selectAll("path")
            .data(links, d => d.target.id);

        // Enter any new links at the parent's previous position.
        const linkEnter = link.enter().append("path")
            .attr("d", d => {
                const o = {x: source.x0, y: source.y0};
                return this._diagonal({source: o, target: o});
            });

        // Transition links to their new position.
        link.merge(linkEnter).transition(transition)
            .attr("d", this._diagonal);

        // Transition exiting nodes to the parent's new position.
        link.exit().transition(transition).remove()
            .attr("d", d => {
                const o = {x: source.x, y: source.y};
                return this._diagonal({source: o, target: o});
            });

        // Stash the old positions for transition.
        this.root.eachBefore(d => {
            d.x0 = d.x;
            d.y0 = d.y;
        });


        // Render synteny

        this.gNode.selectAll("g").filter(function (d, i) {
            return d._children || d.height == 0
        }).each(function (d) {

            var g = d3.select(this).append('g').attr('class', 'g_synteny')
            var idd = d.data.data.id.split('_')[0]

            var level_query = d.data.data.hasOwnProperty('LOFT') ? '' :  '&level=' + d.data.data.species;

            if (that.synteny_data.hasOwnProperty(idd + level_query.replace('&level=', ''))) {


                var l = level_query.replace('&level=', '')

                that.render_synteny(g, that.synteny_data[idd + l].linear_synteny, l, idd )
                return
            }



            $.ajax({

                url: "/api/synteny/" + idd + "/?evidence=linearized&context=" + that.settings.hald_window + level_query,
                dataType: 'json',
                async: true,
                success: function (jsonData) {
                    that.load_and_process_synteny_api(idd, jsonData, false,  level_query.replace('&level=', ''));
                    var l = level_query.replace('&level=', '');

                    that.render_synteny(g, that.synteny_data[idd + l].linear_synteny, l, idd)

                }
            });

        });

    }

    _diagonal(d) {
        return "M" + d.source.y + "," + d.source.x
            + "V" + d.target.x + "H" + d.target.y;
    }

    render_synteny(g_container, data, level, api_id) {

        var that = this


        for (let i = 0; i < data.length; i++) {

            if (data[i] == null) continue

            var e = data[i].hog_id ? data[i].hog_id : data[i].id

            var posL = (this.settings.width_text + this.settings['marginLeftSynteny']) + (i * (this.settings['width_block'] + this.settings['blockMargin']))

            g_container.append("line")
                .style("stroke", "black")
                .attr("x1", posL - this.settings['blockMargin'])
                .attr("x2", posL + this.settings['width_block'] + this.settings['blockMargin'])
                .attr("y1", 0)
                .attr("y2", 0)

            var r = g_container.append("rect")

            r.attr("x", posL)
                .attr("y", -7)
                .attr("width", this.settings['width_block'])
                .attr("height", 15)
                .attr("fill", () => {
                    return this.color_scale(this.get_domain_scale(e))
                })
                .style("stroke-width", 1)
                .style("stroke", () => {
                    return  e.split('.')[0] == this.focal_hog.split('.')[0] ? "black" : "white" // todo
                })
                .style("cursor", "pointer")
                 .on("click", (event, node) => { this._click_square(event, data[i],level)})



            if (data[i].id == api_id){

                g_container.append("text")
            .attr('class', 'rect_upper_label')
            .attr("dy", "18px")
            .attr("x", posL  + this.settings['width_block']/2 )
            .attr("text-anchor", "middle")
            .text(d => {return data[i].id})
            .style('font-size', "10px")
            .style('font-family', 'monospace')
            }

        }

    }

    // TREE

    render_tooltip(x, y, menu) {

        this.Tooltip.style("opacity", 1).style("display", 'block')
            .style("left", x + 12 + "px")
            .style("top", y + 12 + "px")

        this.Tooltip.html('')

        var gg = this.Tooltip.selectAll('menu_item')
            .data(menu)
            .enter().append('text')
            .style('text-align', (d,i) => {return d.title === "Close" ? 'center' : 'start' })
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

    _click_node (event, node, level) {

                var menu = [];

                if (node.data.data.paralog) {

                    var t = {
                        title: 'Duplication',
                        action: null,
                    }

                    var tt = {
                        title: "Duplication node  can't be collapsed",
                        action: () => null
                    }

                    menu.push(t)
                    menu.push(tt)


                }
                else {

                    var t = {
                        title: node.data.data.id.split('_')[0],
                        action: null,
                    }

                    menu.push(t)


                     var ts = {
                    title: node.data.data.species,
                    action: null}


                    menu.push(ts)



                       if (node.children) {
                        var tt = {
                            title: 'Collapse',
                            action: () => {
                                this.toggle_node(node)
                            }
                        }

                        menu.push(tt)
                    } else if (node._children) {

                        var tt = {
                            title: 'Expand',
                            action: () => {
                                this.toggle_node(node)
                            }
                        }

                        menu.push(tt)


                    }

                       var ttcall = {
                            title: 'Collapse All',
                            action: () => {
                                this.collapse_all_node(node)
                            }
                        }

                        menu.push(ttcall)

                    var tteall = {
                            title: 'Expand All',
                            action: () => {
                                this.expand_all_node(node)
                            }
                        }

                        menu.push(tteall)


                    if (node.children || node._children) {

                        var ttt = {
                            title: '<a href=""> Open HOG detail </a>' ,
                            action: () => {
                                this.call_back_hog_detail(node.data.data.id.split('_')[0], level)
                            }
                        }

                        menu.push(ttt)

                        var tttt = {
                            title: '<a href=""> Use as synteny focus </a>',
                            action: () => {
                                this.call_back_hog_local_synteny(node.data.data.id.split('_')[0], level)
                            }
                        }

                        menu.push(tttt)


                    }
                    else {

                        var ttt = {
                            title: '<a href=""> Open gene detail </a>' ,
                            action: () => {
                                this.call_back_gene_detail(node.data.data.id)
                            }
                        }

                        menu.push(ttt)

                        var tttt = {
                            title:  '<a href=""> Use as synteny focus </a>' ,
                            action: () => {
                                this.callback_gene_local_synteny(node.data.data.id)
                            }
                        }
                        menu.push(tttt)
                    }


                }

                var close = {
                    title: 'Close',
                    action: () => {
                        this.close_tooltip()
                    }
                }

                menu.push(close)

                this.render_tooltip(event.offsetX + 12, event.offsetY + 12, menu)

            }

    _click_square (event, data, level) {


        var type  = data.hasOwnProperty('hog_id') ? 'extant' : 'ancestral'

        console.log(data, level)

         var menu = [];

         var t = {title: data.id, action: null }
        menu.push(t)

          if (type == 'ancestral') {

                        var ttt = {
                            title: '<a href=""> Open HOG detail</a>' ,
                            action: () => {
                                this.call_back_hog_detail( data.id.split('_')[0], level)
                            }
                        }

                        menu.push(ttt)

                        var tttt = {
                            title:  '<a href=""> Use as synteny focus </a>' ,
                            action: () => {
                                this.call_back_hog_local_synteny( data.id.split('_')[0], level)
                            }
                        }

                        menu.push(tttt)

               $.ajax({
                url: "/api/hog/" + data.id + "/",
                dataType: 'json',
                async: false,
                success: function (data) {
                        menu.push({title: ` <b>Description: </b>${data[0].description}`, action: null })
                        menu.push({title: `<b>Completeness Score: </b>${data[0].completeness_score.toFixed(2)}`, action: null })
                }
            });




                    }
                    else {

                        var ttt = {
                            title: '<a href=""> Open gene detail </a>' ,
                            action: () => {
                                this.call_back_gene_detail( data.id)
                            }
                        }

                        menu.push(ttt)

                        var tttt = {
                            title: '<a href=""> Use as synteny focus </a>',
                            action: () => {
                                this.callback_gene_local_synteny(data.id)
                            }
                        }
                        menu.push(tttt)

              var genome_release = null

                         $.ajax({

                url: "/api/protein/" + data.id + "/",
                dataType: 'json',
                async: false,
                success: function (data) {
                    genome_release = data.species.species;
                    menu.push({title: `<b> ID:</b> ${data.omaid}`, action: null })
                        menu.push({title: `<b>  OMA ID:</b> ${data.omaid}`, action: null })
                        menu.push({title: `<b> Sequence length:</b> ${data.sequence_length}`, action: null })
                        menu.push({title: `<b> Chromosome:</b> ${data.chromosome}`, action: null })
                        menu.push({title: `<b> Description:</b> ${data.description}`, action: null })
                }
            });

                        $.ajax({

                url: '/api/protein/' + data.id + '/xref/?filter=maindb',
                dataType: 'json',
                async: false,
                success: function (data) {

                    for (var dataKey in data) {
                        var xf = data[dataKey];
                        menu.push({title: `<b>  ${xf['source']}: </b>${xref_format.dbxref_url(xf['xref'], xf['source'], genome_release)}`, action: null })

                    }
                }
            });

                    }


        var close = {
            title: 'Close',
            action: () => {
                this.close_tooltip()
            }
        }

        menu.push(close)

        this.render_tooltip(event.offsetX + 12, event.offsetY + 12, menu)

            }

    // UTILS

    get_domain_scale(query){
        return this.domain_scale.find(hog => query.startsWith(hog))
    }

    render_tooltip_synteny_extant(x, y, id, rect) {

        var that = this;

        $.getJSON("/api/protein/" + id + "/", function (data) {

            that.Tooltip.style("opacity", 1).style("display", 'block')
                .html(`<b>ID:</b> ${data.omaid}  <br>
                    <b>External ID:</b> ${data.canonicalid}  <br> 
                    <b>OMA ID:</b> ${data.omaid}  <br> 
                    <b>sequence length:</b> ${data.sequence_length}  <br> 
                    <b>chromosome:</b> ${data.chromosome}  <br> 
                    <b>description:</b> ${data.description}  <br> 
                    <b>HOG ID:</b> ${data.oma_hog_id}  <br>`)
                .style("left", x + 12 + "px")
                .style("top", y + 12 + "px")

        })

    }

    render_tooltip_synteny_hog(x, y, id, rect) {

        var that = this;

        $.getJSON("/api/hog/" + id + "/", function (data) {

            that.Tooltip.style("opacity", 1).style("display", 'block')
                .html(`<b>ID:</b> ${id}  <br> 
                    <b>Description:</b>  ${data[0].description} <br> `)
                .style("left", x + 12 + "px")
                .style("top", y + 12 + "px")

        })


    }

    close_tooltip() {
        this.Tooltip.style("opacity", 0).style("display", 'none')
    }

    toggle_node(d) {

        if (d.data.data.paralog) return


        if (d.children) {
            d._children = d.children;
            d.children = null;
        } else {
            d.children = d._children;
            d._children = null;
        }
        this.update(event, d);
    }

    collapse_all_node(d) {

        if (d.data.data.paralog) return

        this._traverse(d, null, function (child_done, current_node) {

            if (child_done.data.data.paralog){return}

            if (child_done.children == null ){return}

           child_done._children = child_done.children;
            child_done.children = null;

        })


        if (d.children){
             d._children = d.children;
            d.children = null;
        }



        this.update(event, d);
    }

    expand_all_node(d) {

        if (d.data.data.paralog) return

        this._traverse(d, function (current_node, children_done) {

            if (current_node.data.data.paralog){return}

            if (current_node.children){return}


            current_node.children = current_node._children;
            current_node._children = null;




        }, null)

        if (d.children == null ){
            d.children = d._children;
            d._children = null;}



        this.update(event, d);
    }


    load_and_process_synteny_api(hog_id, jsonData, is_reference, level) {


        // TODO ADD FALLBACK FOR EMPTY OR NOT CORRECT OR ERROR

        var is_reference = is_reference == undefined ? false : is_reference

        var nodes = jsonData['nodes'];
        var edges = jsonData['links'];

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

        if (!( Object.keys(contig.hogs).length === 1)) {

            for (const hogsKey in contig.hogs) {

                var h = contig.hogs[hogsKey];

                switch (Object.keys(h.neighbors).length) {
                    case 0:
                        console.log("No neighbor in this hog")
                        console.log(contig)
                        this.synteny_data[hog_id + level] = contig
                        return
                    case 1:
                        ends.push(h);
                        if (ends.length > 2) {
                            console.log("More than 2 ends in the contigs")
                            this.synteny_data[hog_id+ level] = contig
                            return
                        }
                        break;
                    case 2:
                        break;
                    default:
                        console.log("More than 2 neighboring hogs")
                        this.synteny_data[hog_id+ level] = contig
                        return
                }

            }

            if (ends.length !== 2) {
                console.log("Contigs dont have 2 ends.")
                this.synteny_data[hog_id+ level] = contig
                return

            }

                 // Flatten contig
            var previous = null
            var current = ends[0]
            var processing = true
            var focal_element = null
            var focal_id = is_reference ? this.reference_element : hog_id

            while (processing) {

                contig.linear_synteny.push(current);

                if (current.hog_id && current.hog_id == focal_id) {
                    focal_element = current
                } else if (current.id == focal_id) {
                    focal_element = current
                }

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

        }

        else {
            var g = contig.hogs[Object.keys(contig.hogs)[0]]
            contig.linear_synteny.push(g);
        }

                // INVERT LINEAR SYNTENY

        if (!is_reference && !(Object.keys(contig.hogs).length === 1) ) {

            var level_ = this.focal_hog !== this.reference_element ? '' :  this.focal_species;

            var left_ref = this.synteny_data[this.reference_element + level_ ].linear_synteny.slice(0, this.settings.hald_window).map(data => {
                if (data == null) {
                    return data
                }
                return data.hog_id ? data.hog_id.split('.')[0] : data.id.split('.')[0]
            });
            var right_ref = this.synteny_data[this.reference_element + level_ ].linear_synteny.slice(this.settings.hald_window + 1, this.synteny_data[this.reference_element +  level_ ].linear_synteny.length).map(data => {
                if (data == null) {
                    return data
                }
                return data.hog_id ? data.hog_id.split('.')[0] : data.id.split('.')[0]
            });

            var cptR = 0;
            var cptL = 0;

            for (const key in contig.linear_synteny) {

                var e = contig.linear_synteny[key]

                if (e == null) continue

                e = e.hog_id ? e.hog_id.split('.')[0] : e.id.split('.')[0]

                if (key < this.settings.hald_window) {

                    if (left_ref.includes(e)) cptL++;
                    if (right_ref.includes(e)) cptR++;

                }
            }

            if (cptR > cptL) {
                contig.linear_synteny = contig.linear_synteny.reverse()
            }

        }


        // ADD PADDING FOR MISSING ENDS
        var padding_left = this.settings.hald_window - contig.linear_synteny.indexOf(focal_element)
        padding_left = padding_left > this.settings.hald_window ? this.settings.hald_window : padding_left


        if (padding_left > 0) {
            for (let i = 0; i < padding_left; i++) {
                contig.linear_synteny.unshift(null)
            }
        }

        var padding_right = (this.settings.hald_window * 2 + 1) - contig.linear_synteny.length - padding_left

        if (padding_right > 0) {
            for (let i = 0; i < padding_right; i++) {
                contig.linear_synteny.push(null)
            }
        }



        this.synteny_data[hog_id+ level] = contig


    }

    _traverse(o, func_pre, func_post) {

        if (func_pre) {
            func_pre.apply(this, [o, o["children"]])
        }

        if (o["children"]) {

            for (var c in o["children"]) {

                var child = o["children"][c]

                child = this._traverse(child, func_pre, func_post)

                if (func_post) {
                    func_post.apply(this, [child, o])
                }


            }


        }

        return o

    }

    find_focal_root() {

        console.log(this.hog_tree)

        var hog = null;

        this._traverse(this.hog_tree, function (n, c) {

            if (n.id.split('_')[0] == this.focal_hog && n.species == this.focal_species) {
                hog = n;
            }
        })

        return this.remove_nodes_with_one_child(hog)
    }

    remove_nodes_with_one_child(data) {

        var filtered = data

        var to_remove = []

        this._traverse(filtered, null, function (child_done, current_node) {


            if (child_done.children && child_done.children.length === 1) {

                to_remove.push(child_done);

            }

        })

        for (const toRemoveElement of to_remove) {

            var solo = toRemoveElement.children[0];
            var parent = toRemoveElement.parent

            parent.children = parent.children.filter(function (el) {
                return el != toRemoveElement
            });
            parent.children.push(solo);
            solo.parent = parent;

            //child_done = null;

        }

        return filtered
    }

    format_name(d) {

        if (d.data.data.id.length <= this.settings.length_displayed_name_leaf) return d.data.data.id

        return d.data.data.id.substring(0,this.settings.length_displayed_name_leaf-3 ) + '...';

    }

    format_sub_name(d) {

        var label_text = d.data.data.species ? d.data.data.species : d.data.data.id

        if (label_text.length <= this.settings.length_displayed_name_leaf_sub) return label_text

        return label_text.substring(0,this.settings.length_displayed_name_leaf_sub-3 ) + '...';

    }

    is_visible(d) {
        return (d._children || d.height == 0)
    }

    get_root_hog_id(e) {
        return e ? (e.hog_id ? e.hog_id.split('.')[0] : e.id.split('.')[0]) : null
    }

    get_hog_id(e) {
        return e ? (e.hog_id ? e.hog_id : e.id) : null
    }


}