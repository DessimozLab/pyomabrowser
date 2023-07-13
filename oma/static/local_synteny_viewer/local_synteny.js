class LocalSyntenyViewer {

    constructor(div_id, hog_tree, focus, species) {

        // MODEL
        this.hog_tree = hog_tree
        this.focal_hog = focus
        this.focal_species = species
        this.data = d3.hierarchy(this.find_focal_root());

        //VIEWER
        this.div_id = div_id;
        this.div = d3.select("#" + this.div_id);


        // CONTROLLER
        this.settings = {
            marginTop: 80,
            marginRight: 10,
            marginBottom: 10,
            marginLeft: 40,
            width_board: document.getElementById(this.div_id).offsetWidth,
            width_tree: 300,
            width_text: 100,
            dx: 20,
        }

        this.root = d3.hierarchy(this.data);
        this.settings['dy'] = (this.settings.width_tree - this.settings.marginRight - this.settings.marginLeft) / (1 + this.root.height)

        this.tree = d3.cluster().nodeSize([this.settings.dx, this.settings.dy]).separation(function(a, b) {
  return 1;
})
        this.tree(this.root);


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

        this.root.x0 = this.settings.dy / 2;
        this.root.y0 = 0;
        this.root.descendants().forEach((d, i) => {
            d.id = i;
            d._children = null;
        });

        this.update(null, this.root);

        this.svg.node();

    }

    // UTILS
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

    update(event, source) {

        var diagonal = function (d) {
            return "M" + d.source.y + "," + d.source.x
                + "V" + d.target.x + "H" + d.target.y;
        }

        const duration = event?.altKey ? 2500 : 250; // hold the alt key to slow down the transition
        const nodes = this.root.descendants().reverse();
        const links = this.root.links();

        // Compute the new tree layout.
        this.tree(this.root);

        this.root.eachBefore(node => {
            if (node.height === 0 || node._children  ){
                node.y = this.settings.width_tree - this.settings.marginLeft
            }
        });


        let left = this.root;
        let right = this.root;
        this.root.eachBefore(node => {
            if (node.x < left.x) left = node;
            if (node.x > right.x) right = node;
        });

        const height = right.x - left.x + this.settings.marginTop + this.settings.marginBottom;

        d3.select("#ref_line").remove();

        this.svg.append('rect')
            .attr('id', 'ref_line')
          .attr('x', this.settings.width_tree + this.settings.width_text + 4  - this.settings.marginLeft )
          .attr('y', left.x - 40 )
          .attr('width', this.settings.width_board - this.settings.width_tree - this.settings.width_text - this.settings.marginRight - this.settings.marginLeft)
          .attr('height', 20)
          .attr('fill', 'red');


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
            .attr("r", d => d.children && d.children.length === 1 ? 0: 2.5) // TODO REMOVE THIS BUG
            .attr("fill", d => d._children ? "#555" : "#999")
            .attr("stroke-width", 10);


        nodeEnter.append("text")
            .attr("dy", "0.31em")
            .attr("x", 6)
            .attr("text-anchor", "start")
            .text(d => { return d.data.data.id.substring(0, 10);})
            .style('font-size',  "10px")
          .clone(true).lower()
            .attr("stroke-linejoin", "round")
            .attr("stroke-width", 3)
            .attr("stroke", "white");

        nodeEnter.append('rect')
          .attr('x', this.settings.width_text + 4)
          .attr('y', -3)
          .attr('width', this.settings.width_board - this.settings.width_tree - this.settings.width_text - this.settings.marginRight - this.settings.marginLeft)
          .attr('height', 6)
          .attr('stroke', 'black')
          .attr('fill', '#69a3b2');


        // Transition nodes to their new position.
        const nodeUpdate = node.merge(nodeEnter)

            nodeUpdate.transition(transition)
            .attr("transform", d => `translate(${d.y},${d.x})`)
            .attr("fill-opacity", 1)
            .attr("stroke-opacity", 1)

        nodeUpdate.selectAll('text').style('font-size', d => { return d._children || d.height == 0 ? '12px' : '0px'})
        nodeUpdate.selectAll('rect').style('visibility', d => { return d._children || d.height == 0 ? "visible" : "hidden"})

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
                return diagonal({source: o, target: o});
            });

        // Transition links to their new position.
        link.merge(linkEnter).transition(transition)
            .attr("d", diagonal);

        // Transition exiting nodes to the parent's new position.
        link.exit().transition(transition).remove()
            .attr("d", d => {
                const o = {x: source.x, y: source.y};
                return diagonal({source: o, target: o});
            });

        // Stash the old positions for transition.
        this.root.eachBefore(d => {
            d.x0 = d.x;
            d.y0 = d.y;
        });
    }

}