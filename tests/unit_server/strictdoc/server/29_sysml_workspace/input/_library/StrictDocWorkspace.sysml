library package StrictDocWorkspace {
    private import ScalarValues::*;

    metadata def Model { attribute title : String; }
    metadata def Tracker { attribute title : String; attribute kind : String; attribute prefix : String; }
    metadata def Folder { attribute title : String; }
    metadata def DiagramView { attribute options : String; attribute plantuml : String; }
}
