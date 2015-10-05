"use strict";
var tnt_theme_tree_hog = function () {

    var height = 30;
    var curr_taxa = '';
    var annot;
    var is_node_frozen = false;
    // var collapsed_nodes = [];

    var theme = function (ta, div, query, per_species3, tree_obj, gene_data, options) {
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
        var node_display = tnt.tree.node_display.cond()
            .add("highlight", function (node) {
            return false;
        }, highlight_node)
            .add("collapsed", function (node) {
            return node.is_collapsed();
        }, collapsed_node)
            .add("leaf", function (node) {
            return node.is_leaf();
        }, leaf_node)
            .add("internal", function (node) {
            return !node.is_leaf();
        }, int_node);
        var tot_width = parseInt(d3.select(div).style("width")) - 30;

        // Tooltips
        var node_tooltip = function (node) {
            var obj = {};
            obj.header = node.node_name();
            obj.rows = [];
            obj.rows.push({
                label: 'Freeze',
                link: function (node) {
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
                        ta.update();
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
                        ta.update();
                    },
                    obj: node,
                    value: "Collapse subtree"
                });
            }
            tnt.tooltip.table().call(this, obj);
        };

        // mouse over a node
        var mouse_over_node = function (node) {
            // Update annotation board
            if (is_node_frozen){
                return;
            }
            var name = node.node_name();
            curr_taxa = name;
            annot.update();


            var highlight_condition = function (n) {
                return node.id() === n.id();
            };
            node_display.update("highlight", highlight_condition, highlight_node);

            ta.update();
        };

        var tree = tnt.tree()
            .data(tree_obj)
            .layout(tnt.tree.layout.vertical()
                .width(Math.max(200, ~~(tot_width * 0.4)))
                .scale(false)
        )
            .label(tnt.tree.label.text()
                .fontsize(12)
                .height(height)
                .text(function (node) {
                var limit = 30;
                var data = node.data();
                if (node.is_collapsed()) {
                    return "[" + node.n_hidden() + " hidden taxa]";
                }
                if (!options.show_internal_labels && data.children && data.children.length > 0) {
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
        )
            .link_color("black")
            .on_mouseover(mouse_over_node)
            .on_click(node_tooltip)
            .node_display(node_display)
            .link_color("black");

        curr_taxa = tree.root().node_name();

        /////////////////////////
        //// PARSE HOG INFO /////
        /////////////////////////
        var maxs = get_maxs(per_species3);
        var gene_tooltip = function (gene) {
            var obj = {};
            obj.header = gene_data[gene.id].omaid;
            obj.rows = [];
            obj.rows.push({label: "Name", value: gene_data[gene.id].id});
            obj.rows.push({
                label: "Information",
                link: function (gene) {
                    window.location = options.oma_info_url_template + gene.id;
                    return
                },
                obj: gene, value: gene_data[gene.id].omaid
            });

            tnt.tooltip.table().call(this, obj);
        };

        // TnT doesn't have the features we need, so create our own
        var hog_feature = tnt.track.feature()
            .index(function (d) {
            return d.id;
        })
            .create(function (new_hog, x_scale) {
            var track = this;
            var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??
            // otherwise it is repeated with every create event

            var new_boundary = new_hog
                .append("line")
                .attr("class", "hog_boundary")
                .attr("x1", function (d, i) {
                return (d.total_genes * track.height()) + (d.hog * 20) + 10;
            })
                .attr("x2", function (d, i) {
                return (d.total_genes * track.height()) + (d.hog * 20) + 10;
            })
                .attr("y1", 0)
                .attr("y2", track.height())
                .attr("stroke-width", 2)
                .attr("stroke", "black");
        })
            .updater(function (hogs, x_scale) {
            var track = this;
            var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??

            hogs.select("line")
                .transition()
                .attr("x1", function (d, i) {
                    return (d.total_genes * track.height()) + (d.hog * 20) + 10;
                })
                .attr("x2", function (d, i) {
                    return (d.total_genes * track.height()) + (d.hog * 20) + 10;
                });
        });

        var hog_gene_feature = tnt.track.feature()
            .index(function (d) {
            return d.id;
        })
            .create(function (new_elems, x_scale) {
            var track = this;
            var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??
            // otherwise it is repeated with every create event
            var side = track.height() - ~~(padding * 2);

            new_elems
                .append("rect")
                .attr("class", "hog_gene")
                .attr("x", function (d) {
                return (d.pos * track.height()) + (d.hog * 20) + padding;
            })
                .attr("y", padding)
                .attr("width", side)
                .attr("height", side)
                .attr("fill", function (d) {
                return (d.id == query.id ? "green" : "grey");
            });
        })
            .on_mouseover(gene_tooltip)
            .updater(function (elems, x_scale) {
            var track = this;
            var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??
            // otherwise it is repeated with every create event
            var side = track.height() - ~~(padding * 2);

            elems.select("rect")
                .transition()
                .attr("x", function (d) {
                    return (d.pos * track.height()) + (d.hog * 20) + padding;
                });
        });

        annot = tnt.board()
            .from(0)
            .zoom_in(1)
            .allow_drag(false)
            .to(5)
            .width(~~(tot_width * 0.6))
            .right(5);

        var track = function (leaf) {
            var sp = leaf.node_name();
            return tnt.track()
                .background_color('#E8E8E8')
                .data(tnt.track.data()
                    .update(tnt.track.retriever.sync()
                        .retriever(function () {
                        // return _.flatten(per_species2[sp].Vertebrates);
                        // return per_species2[sp].Vertebrates;
                        if (per_species3[sp] === undefined) {
                            return {
                                genes: [],
                                hogs: []
                            };
                        }
                        return genes_2_xcoords(per_species3[sp][curr_taxa], maxs[curr_taxa]);
                    })
                )
            )
                .display(tnt.track.feature.composite()
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
                hog_genes.forEach(function(gene, gene_pos){
                    genes.push({
                        id: gene,
                        hog: hog,
                        pos: total_pos+gene_pos,
                        max_in_hog: maxs[hog],
                        pos_in_hog: gene_pos
                    });
                    hog_gene_names.push(gene);
                });
                total_pos += maxs[hog];
                hogs_boundaries.push({
                    total_genes: total_pos,
                    hog: hog,
                    id: hog_gene_names.length ? hog_gene_names.join('_') : ("hog_" + hog)
                });
            });

            return {
                genes: genes,
                hogs: hogs_boundaries
            };
        };

        ta.tree(tree);
        ta.annotation(annot);
        ta.track(track);
        ta(div);

    };

    // converts the argument into an arrays
    // if the argument is already an array, just returns it
    // NOTE: AFAIK, this is not used now
    var obj2array = function (o) {
        if (o === undefined) {
            return [];
        }

        if (Object.prototype.toString.call(o) === '[object Array]') {
            return o;
        }

        return [o];
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

