// __SLUG___v__N__Engine.js - processing logic, no GUI objects allowed here.
//
// Contract used by the GUI and by the headless test harness:
//   new PSWParameters()        -> object with defaults, .load(), .save()
//   PSWEngine.run(view, params) -> processes view in place (with undo),
//                                  returns an object with numbers worth logging

var PSWParameters = class
{
   constructor()
   {
      // Every tunable value with a sane default.
      this.amount = 0.5;
   }

   load()
   {
      let v = Settings.read( PSW_SETTINGS + "/amount", DataType.Double );
      if ( Settings.lastReadOK )
         this.amount = v;
   }

   save()
   {
      Settings.write( PSW_SETTINGS + "/amount", DataType.Double, this.amount );
   }
};

var PSWEngine = {
   run: function( view, params )
   {
      if ( view == null || view.isNull )
         throw new Error( "PSWEngine.run: invalid view" );

      // Prefer built-in processes (PixelMath, CurvesTransformation, ...) over
      // per-pixel JavaScript loops: they are much faster and handle undo.
      let P = new PixelMath;
      P.expression = "$T*(1-" + params.amount + ") + " + params.amount + "*$T^2";
      P.useSingleExpression = true;
      P.createNewImage = false;
      P.rescale = false;
      P.truncate = true;
      P.executeOn( view );

      return { median: view.image.median() };
   }
};
