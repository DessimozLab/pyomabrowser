class LocalSyntenyViewer {

    constructor(div_id, hog_tree, focus, species) {

        var that = this // ugly handle for non-arrow function usage

        // MODEL
        this.hog_tree = hog_tree
        this.focal_hog = focus
        this.focal_species = species
        this.data = d3.hierarchy(this.find_focal_root());
        this.synteny_data = {}

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
            width_tree: 300,
            width_text: 100,
            // UI TREE
            dx: 40,
            circle_radius: 4,
            circle_radius_leaf: 3,
            length_displayed_name_leaf: 10,
            // UI SYNTENY
            height_synteny: 20,
            ref_synteny_bottomMargin: 30,
            blockMargin: 6,
            marginLeftSynteny: 20,
            color_scheme: ['#9e0142', '#d53e4f', 'salmon', '#f46d43', '#fdae61', '#fee08b', '#e6f598', '#abdda4', '#66c2a5', '#3288bd', '#5e4fa2']
        }

        this.settings['width_block'] = -6 + (document.getElementById(this.div_id).offsetWidth - this.settings['width_tree'] - this.settings['marginLeftSynteny'] - this.settings['width_text']) / (1 + 2 * (this.settings['hald_window']))

        // LOAD THE FOCAL HOG SYNTENY
        $.ajax({
            url: "https://oma-stage.vital-it.ch/api/synteny/" + that.focal_hog + "/?evidence=linearized&context=" + that.settings.hald_window,
            dataType: 'json',
            async: false,
            success: function (jsonData) {

                that.load_and_process_synteny_api(that.focal_hog, jsonData, true)

                var ln = that.synteny_data[that.focal_hog].linear_synteny.map(hog => that.get_root_hog_id(hog))

                that.color_scale = d3.scaleOrdinal().domain(ln).range(that.settings['color_scheme'].splice(that.synteny_data[that.focal_hog].linear_synteny.length - ln.length)).unknown("lightgrey");

            }
        });

        if (!this.synteny_data[this.focal_hog]){
            this.div.append("p").text('No synteny is available for this HOG or gene.')
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
            .attr("style", "max-width: 100%; height: auto; font: 10px sans-serif; user-select: none;");

        this.gLink = this.svg.append("g")
            .attr("fill", "none")
            .attr("stroke", "#555")
            .attr("stroke-opacity", 0.4)
            .attr("stroke-width", 1.5);

        this.gNode = this.svg.append("g")
            .attr("cursor", "pointer")
            .attr("pointer-events", "all");

        // init the d3 tree model
        this.root = d3.hierarchy(this.data);

        // Apply the d3 layout to the model
        this.settings['dy'] = (this.settings.width_tree - this.settings.marginRight - this.settings.marginLeft) / (1 + this.root.height)
        this.tree = d3.cluster()
            .nodeSize([this.settings.dx, this.settings.dy])
            .separation(function (a, b) {return 1;})

        // Build and init the tree viewer instance
        this.tree(this.root);
        this.root.x0 = this.settings.dy / 2;
        this.root.y0 = 0;
        this.root.descendants().forEach((d, i) => {d.id = i;d._children = null;});

        // First rendering
        this.update(null, this.root);

    }

    // VIEWER

    update(event, source) {

        var that = this // UGLY HANDLE

        d3.selectAll(".g_synteny").remove();

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
        var x_ref = this.settings.width_tree + this.settings.width_text - this.settings.marginLeft
        var y_ref = left.x - this.settings.height_synteny - this.settings.ref_synteny_bottomMargin
        var ref_synteny_g = this.svg.append('g').attr('id', 'ref_line')
            .attr("transform", () => { return "translate(" + x_ref + ", " + y_ref + ")" })
        this.render_synteny(ref_synteny_g, this.synteny_data[this.focal_hog].linear_synteny)


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
            .on("click", (event, d) => {
                // TODO TOOL TIP + MENU
                if (d.children) {
                    d._children = d.children;
                    d.children = null;
                } else {
                    d.children = d._children;
                    d._children = null;
                }
                this.update(event, d);
            });

        nodeEnter.append("circle")
            .attr("r", d => d.children && d.children.length === 1 ? 0 : d.children ? this.settings.circle_radius : this.settings.circle_radius_leaf) // TODO REMOVE THIS BUG
            .attr("fill", d => d._children || d.children ? "#555" : "#999")
            .attr("stroke-width", 10);

        nodeEnter.append("text")
            .attr("dy", "0.31em")
            .attr("x", 6)
            .attr("text-anchor", "start")
            .text(d => this.format_name(d))
            .style('font-size', "10px")
            .style('font-family', 'monospace')
            .clone(true).lower()
            .attr("stroke-linejoin", "round")
            .attr("stroke-width", 3)
            .attr("stroke", "white");

        // Transition nodes to their new position.
        const nodeUpdate = node.merge(nodeEnter)

        nodeUpdate.transition(transition)
            .attr("transform", d => `translate(${d.y},${d.x})`)
            .attr("fill-opacity", 1)
            .attr("stroke-opacity", 1)

        nodeUpdate.selectAll('text').style('font-size', d => { return d._children || d.height == 0 ? '14px' : '0px'})

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

        this.gNode.selectAll("g").filter(function (d, i) {return d._children || d.height == 0}).each(function (d) {

            var g = d3.select(this).append('g').attr('class', 'g_synteny')
            var idd = d.data.data.id.split('_')[0]

            if (that.synteny_data.hasOwnProperty(idd)) {
                that.render_synteny(g, that.synteny_data[idd].linear_synteny)
                return
            }

            $.ajax({
                url: "https://oma-stage.vital-it.ch/api/synteny/" + idd + "/?evidence=linearized&context=" + that.settings.hald_window,
                dataType: 'json',
                async: true,
                success: function (jsonData) {
                    that.load_and_process_synteny_api(idd, jsonData);
                    that.render_synteny(g, that.synteny_data[idd].linear_synteny)

                }
            });

        });

    }

    _diagonal(d) {
            return "M" + d.source.y + "," + d.source.x
                + "V" + d.target.x + "H" + d.target.y;
        }

    render_synteny(g_container, data) {

        for (let i = 0; i < data.length; i++) {

            if (data[i] == null) continue

            var e = data[i].hog_id ? data[i].hog_id : data[i].id

            var posL = this.settings['marginLeftSynteny'] + i * (this.settings['width_block'] + this.settings['blockMargin'])

            g_container.append("line")
                .style("stroke", "black")
                .attr("x1", posL - this.settings['blockMargin'])
                .attr("x2", posL + this.settings['width_block'] + this.settings['blockMargin'])
                .attr("y1", 0)
                .attr("y2", 0)

            g_container.append("rect")
                .attr("x", posL)
                .attr("y", -7)
                .attr("width", this.settings['width_block'])
                .attr("height", 15)
                .attr("fill", () => {
                    return this.color_scale(e.split('.')[0])
                })
                .style("stroke-width", 1)
                .style("stroke", () => {
                    return e.split('.')[0] == this.focal_hog.split('.')[0] ? "black" : "white"
                })

        }

    }

    // UTILS

    load_and_process_synteny_api(hog_id, jsonData, is_reference) {


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

        for (const hogsKey in contig.hogs) {

            var h = contig.hogs[hogsKey];

            switch (Object.keys(h.neighbors).length) {
                case 0:
                    console.log("No neighbor in this hog")
                    this.synteny_data[hog_id] = contig
                    return
                case 1:
                    ends.push(h);
                    if (ends.length > 2) {
                        console.log("More than 2 ends in the contigs")
                        this.synteny_data[hog_id] = contig
                        return

                    }
                    break;
                case 2:
                    break;
                default:
                    console.log("More than 2 neighboring hogs")
                    this.synteny_data[hog_id] = contig
                    return
            }

        }

        if (ends.length !== 2) {
            console.log("Contigs dont have 2 ends.")
            this.synteny_data[hog_id] = contig
            return

        }

        // Flatten contig
        var previous = null
        var current = ends[0]
        var processing = true
        var focal_element = null

        while (processing) {

            contig.linear_synteny.push(current);

            if (current.hog_id && current.hog_id == hog_id) {
                focal_element = current
            } else if (current.id == hog_id) {
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

        // ADD PADDING FOR MISSING ENDS
        var padding_left = this.settings.hald_window - contig.linear_synteny.indexOf(focal_element)

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


        // INVERT LINEAR SYNTENY

        if (!is_reference) {

            console.log(this.synteny_data[this.focal_hog].linear_synteny)

            var left_ref = this.synteny_data[this.focal_hog].linear_synteny.slice(0, this.settings.hald_window).map(data => {
                if (data == null) {
                    return data
                }
                return data.hog_id ? data.hog_id.split('.')[0] : data.id.split('.')[0]
            });
            var right_ref = this.synteny_data[this.focal_hog].linear_synteny.slice(this.settings.hald_window + 1, this.synteny_data[this.focal_hog].linear_synteny.length).map(data => {
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

            console.log(hog_id, cptR, cptL, left_ref, right_ref)

            if (cptR > cptL) {
                contig.linear_synteny = contig.linear_synteny.reverse()
            }

        }

        this.synteny_data[hog_id] = contig


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

        this._traverse(filtered, null, function (child_done, current_node) {

            if (child_done.children && child_done.children.length === 1) {

                var solo = child_done.children[0];

                current_node.children = current_node.children.filter(function (el) {
                    return el != child_done
                });
                current_node.children.push(solo);
                solo.parent = current_node;

                child_done = null;


            }

        })

        console.log(filtered)

        return filtered
    }

    format_name(d) {

        if (d.data.data.id.length <= this.settings.length_displayed_name_leaf) return d.data.data.id

        return d.data.data.id.substring(0, 7) + '...';

    }

    is_visible(d) {
        return (d._children || d.height == 0)
    }

    get_root_hog_id(e){
        console.log(e)
        return e  ? (e.hog_id ? e.hog_id.split('.')[0] : e.id.split('.')[0]) : null
    }


}