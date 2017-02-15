"use strict";
var hog_theme = function () {

    var label_height = 30;
    var curr_taxa = '';
    var annot;
    var is_node_frozen = false;
    // var collapsed_nodes = [];
    var fam_genedata;
    var genedatavis = [{
            name: 'Query Gene',
            scale: 'on_off'
        },
        {
            name: "Gene Length",
            scale: "linear",
            field: "sequence_length",
            func: "color1d"
        },
        {
            name: "EC Content",
            scale: "linear",
            field: "ec_content",
            func: "color1d"
        }
    ];

    var theme = function (div, query, per_species3, tree_obj, gene_data, options, genedata_picker_div) {
        /////////////
        // TREE /////
        /////////////

        // Nodes shapes / colors
        var collapsed_node = tnt.tree.node_display.triangle()
            .fill("grey")
            .size(4);
        var leaf_node = tnt.tree.node_display.circle()
            .fill("black")
            .size(4);
        var int_node = tnt.tree.node_display.circle()
            .fill("black")
            .size(2);
        var highlight_node = tnt.tree.node_display.circle()
            .fill("brown")
            .size(6);
        var highlight_condition = function(){
            return false;
        };
        var gene_color_function;

        var node_display = tnt.tree.node_display()
            .display(function (node){
                if (highlight_condition(node)){
                    highlight_node.display().call(this, node);
                } else if (node.is_collapsed()){
                    collapsed_node.display().call(this, node);
                } else if (node.is_leaf()){
                    leaf_node.display().call(this, node);
                } else if (!node.is_leaf()) {
                    int_node.display().call(this, node);
                }
            });

        var tot_width = parseInt(d3.select(div).style("width")) - 30;

        // Tooltips
        var node_tooltip = function (node) {
            var obj = {};
            obj.header = node.node_name();
            obj.rows = [];
            obj.rows.push({
                label: 'Freeze',
                link: function () {
                    is_node_frozen = !is_node_frozen;
                },
                obj: node,
                value: is_node_frozen ? "Unfreeze tree node" : "Freeze tree node"
            });

            if (node.is_collapsed()) {
                obj.rows.push({
                    label: 'Action',
                    link: function (node) {
                        node.toggle();
                        vis.update();
                    },
                    obj: node,
                    value: "Uncollapse subtree"
                });
            }

            if (!node.is_leaf()) {
                obj.rows.push({
                    label: 'Action',
                    link: function (node) {
                        node.toggle();
                        vis.update();
                    },
                    obj: node,
                    value: "Collapse subtree"
                });
            }
            tnt.tooltip.table().call(this, obj);
        };

        // mouse over a node
        var node_hover_tooltip;
        var mouse_over_node = function (node) {
            // Update annotation board
            if (is_node_frozen){
                return;
            }

            curr_taxa = node.node_name();
            annot.update();

            highlight_condition = function (n) {
                return node.id() === n.id();
            };
            tree.update_nodes();

            // Show a mouse over tooltip for internal nodes
            if (!options.show_internal_labels && node.data().children && node.data().children.length) {
                var obj = {};
                obj.header = "";
                obj.body = node.node_name();
                node_hover_tooltip = tooltip.plain()
                    .width(140)
                    .show_closer(false)
                    .call(this, obj);
            }
        };

        // node mouseout
        var mouse_out_node = function (node) {
            if (!options.show_internal_labels) {
                node_hover_tooltip.close();
            }
        };

        var tree = tnt.tree()
            .data(tree_obj)
            .layout(tnt.tree.layout.vertical()
                .width(Math.max(200, ~~(tot_width * 0.4)))
                .scale(false)
               )
            .label(tnt.tree.label.text()
                .fontsize(12)
                .height(label_height)
                .text(function (node) {
                    var limit = 30;
                    var data = node.data();
                    if (node.is_collapsed()) {
                        return "[" + node.n_hidden() + " hidden taxa]";
                    }
                    if ((!options.show_internal_labels || !highlight_condition(node)) &&
                        data.children && data.children.length > 0) {
                        return "";
                    }
                    if (data.name.length > limit) {
                        var truncName = data.name.substr(0,limit-3) + "...";
                        return truncName.replace(/_/g, ' ');
                    }
                    return data.name.replace(/_/g, ' ');
                })
                .color(function (node) {
                    if (node.is_collapsed()) {
                        return 'grey';
                    }
                    return 'black';
                })
                .fontweight(function (node){
                    if (highlight_condition(node)){
                        return "bold";
                    }
                    return "normal";
                })
               )
            .on("click", node_tooltip)
            .on("mouseover", mouse_over_node)
            .on("mouseout", mouse_out_node)
            .node_display(node_display)
            .branch_color("black");

        curr_taxa = tree.root().node_name();

        /////////////////////////
        //// PARSE HOG INFO /////
        /////////////////////////
        var maxs = get_maxs(per_species3);
        var gene_color_data;

        var gene_tooltip = function (gene) {
            var obj = {};
            obj.header = gene_data[gene.id].omaid;
            obj.rows = [];
            obj.rows.push({label: "Name", value: gene_data[gene.id].id});
            obj.rows.push({
                label: "Information",
                link: function (gene) {
                    window.location = options.oma_info_url_template + gene.id;
                },
                obj: gene, value: gene_data[gene.id].omaid
            });

            tnt.tooltip.table().call(this, obj);
        };

        // TnT doesn't have the features we need, so create our own
        // This one if for the lines defining hogs
        var hog_feature = tnt.board.track.feature();
        hog_feature
            .index(function (d) {
                return d.id;
            })
            .create(function (new_hog, x_scale) {
                var track = this;
                var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??
                // otherwise it is repeated with every create event

                var height = track.height() - ~~(padding * 2);
                var dom1 = x_scale.domain()[1];

                new_hog
                    .append("line")
                    .attr("class", "hog_boundary")
                    .attr("x1", function (d) {
                        var width = d3.min([x_scale(dom1/d.max), height+2*padding]);
                        var x = width * (d.max_in_hog-1);
                        var xnext = width * d.max_in_hog;
                        return x + (xnext - x + width)/2 + ~~(padding/2)-1;
                    })
                    .attr("x2", function (d) {
                        var width = d3.min([x_scale(dom1/d.max), height+2*padding]);
                        var x = width * (d.max_in_hog-1);
                        var xnext = width * d.max_in_hog;
                        return x + (xnext - x + width)/2 + ~~(padding/2)-1;
                    })
                    .attr("y1", 0)
                    .attr("y2", track.height())
                    .attr("stroke-width", 2)
                    .attr("stroke", "black");
            })
            .distribute(function (hogs, x_scale) {
                var track = this;
                var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??

                var height = track.height() - ~~(padding * 2);
                var dom1 = x_scale.domain()[1];

                hogs.select("line")
                    .transition()
                    .duration(200)
                    .attr("x1", function (d) {
                        var width = d3.min([x_scale(dom1/d.max), height+2*padding]);
                        var x = width * (d.max_in_hog-1);
                        var xnext = width * d.max_in_hog;
                        return x + (xnext - x + width)/2 + ~~(padding/2)-1;
                    })
                    .attr("x2", function (d) {
                        var width = d3.min([x_scale(dom1/d.max), height+2*padding]);
                        var x = width * (d.max_in_hog-1);
                        var xnext = width * d.max_in_hog;
                        return x + (xnext - x + width)/2 + ~~(padding/2)-1;
                    });
            });

        var hog_gene_feature = tnt.board.track.feature();
        var gene_color_scale = d3.scale.category10();

        hog_gene_feature
            .index(function (d) {
                return d.id;
            })
            .create(function (new_elems, x_scale) {
                var track = this;
                var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??
                // otherwise it is repeated with every create event

                var height = track.height() - ~~(padding * 2);
                var dom1 = x_scale.domain()[1];

                new_elems
                    .append("rect")
                    .attr("class", function(d) {
                        return "hog_gene" + (query && d.id === query.id ? " ref_gene": "" )
                    })
                    .attr("x", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height+2*padding]);
                        var x = width * d.pos;
                        return x + padding;
                    })
                    .attr("y", padding)
                    .attr("width", function(d){
                        var width = d3.min([x_scale(dom1 / d.max), height+2*padding]);
                        return width - 2*padding;
                    })
                    .attr("height", height)
                    .attr("fill", gene_color_function);
            })
            .distribute(function (elems, x_scale) {
                var track = this;
                var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??
                // otherwise it is repeated with every create event

                var height = track.height() - ~~(padding * 2);
                var dom1 = x_scale.domain()[1];

                elems.select("rect")
                    .transition()
                    .duration(200)
                    .attr("x", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height + 2*padding]);
                        var x = width * d.pos;
                        return x + padding;
                    })
                    .attr("width", function(d){
                        var width = d3.min([x_scale(dom1 / d.max), height+2*padding]);
                        return width - 2*padding;
                    })
                    .attr("fill", gene_color_function);

            })
            .on("mouseover", gene_tooltip);

        annot = tnt.board()
            .from(0)
            .zoom_in(1)
            .allow_drag(false)
            .to(5)
            .width(~~(tot_width * 0.6));


        var track = function (leaf) {
            var sp = leaf.node_name();
            return tnt.board.track()
                .color("#EEEEEE")
                .data(tnt.board.track.data.sync()
                    .retriever(function () {
                        // return _.flatten(per_species2[sp].Vertebrates);
                        // return per_species2[sp].Vertebrates;
                        if (per_species3[sp] === undefined) {
                            return {
                                genes: [],
                                hogs: []
                            };
                        }
                        var genes2Xcoords = genes_2_xcoords(per_species3[sp][curr_taxa], maxs[curr_taxa]);
                        return genes2Xcoords;
                    })

                )
                .display(tnt.board.track.feature.composite()
                    .add("genes", hog_gene_feature)
                    .add("hogs", hog_feature)
                );
        };

        var genes_2_xcoords = function (arr, maxs) {
            if (arr === undefined) {
                return {
                    genes: [],
                    hogs: []
                };
            }
            var genes = [];
            var hogs_boundaries = [];
            var total_pos = 0;
            arr.forEach(function(hog_genes, hog){
                var hog_gene_names = [];
                hog_genes.sort();
                hog_genes.forEach(function(gene, gene_pos){
                    genes.push({
                        id: gene,
                        hog: hog,
                        pos: total_pos+gene_pos,
                        max: d3.sum(maxs),
                        max_in_hog: maxs[hog],
                        pos_in_hog: gene_pos
                    });
                    hog_gene_names.push(gene);
                });
                total_pos += maxs[hog];
                hogs_boundaries.push({
                    max: d3.sum(maxs),
                    max_in_hog: total_pos,
                    hog: hog,
                    id: hog_gene_names.length ? hog_gene_names.join('_') : ("hog_" + hog)
                });
            });

            return {
                genes: genes,
                hogs: hogs_boundaries.slice(0,-1)
            };
        };

        var col_scale;
        var change_genedata_vis = function(d){
            col_scale = undefined;
            gene_color_function = function(gene){
                return (query && gene.id === query.id ? "green" : "gray");
            };
            if (fam_genedata === undefined){
                $.getJSON("/oma/hogdata/"+query.id+"/json", function(data){
                    fam_genedata = {};
                    data.forEach(function(gene) {
                        fam_genedata[gene.id] = gene;
                    });
                    change_genedata_vis(d);
                });
                return;
            }

            var field = d.field;
            if (d.func === "color1d") {
                col_scale = d3.scale.linear()
                    .domain(d3.extent(d3.values(fam_genedata)
                        .map(function (gene){
                            return gene[field];
                        })))
                    .range(["red", "blue"]);
                gene_color_function = function (gene) {
                    return col_scale(fam_genedata[gene.id][field]);
                };
            };
            vis.update();
        };

        change_genedata_vis(genedatavis[0]);
        var genedata_picker = d3.select(genedata_picker_div).selectAll(".genedata-button")
            .data(genedatavis);
        var colorbar;
        var bar = d3.select("#colorbar");

        genedata_picker.enter()
            .append("input")
            .attr("value", function(d){ return d.name })
            .attr("type", "button")
            .attr("class", "genedata-button")
            .on("click", function(d) {
                change_genedata_vis(d);
                if (col_scale) {
                    colorbar = Colorbar()
                        .origin([Math.max(200, ~~(tot_width * 0.4)), 0])
                        .scale(col_scale)
                        .orient('horizontal')
                        .thickness(18)
                        .barlength(~~(tot_width * 0.6));
                    bar.call(colorbar);
                } else {
                    bar.selectAll("svg").remove();
                }
            });



        var vis = tnt()
            .tree(tree)
            .board(annot)
            .track(track);
        vis(div);
    };

    var truncate = function (text, width) {
        text.each(function () {
            var text = d3.select(this),
                full_text = text.text(),
                low = 0, up = full_text.length, m;
            if (text.node().getComputedTextLength() > width) {
                while (low < up) {
                    m = ~~((low + up) / 2);
                    text.text(full_text.slice(0, m) + "...");
                    if (text.node().getComputedTextLength() < width) {
                        low = m;
                    } else {
                        up = m;
                    }
                }
            }
        })
    }

    // get maximum number of genes per hog accross species
    var get_maxs = function (ps2) {
        var maxs = {};
        var i, sp, internal;
        for (sp in ps2) {
            if (ps2.hasOwnProperty(sp)) {
                var sp_data = ps2[sp];
                for (internal in sp_data) {
                    if (maxs[internal] === undefined) {
                        maxs[internal] = [];
                    }
                    if (sp_data.hasOwnProperty(internal)) {
                        var internal_data = sp_data[internal];
                        for (i = 0; i < internal_data.length; i++) {
                            if ((maxs[internal][i] === undefined) ||
                                (maxs[internal][i] < internal_data[i].length)) {
                                maxs[internal][i] = internal_data[i].length;
                            }
                        }
                    }
                }
            }
        }
        return maxs;
    };

    return theme;
};
