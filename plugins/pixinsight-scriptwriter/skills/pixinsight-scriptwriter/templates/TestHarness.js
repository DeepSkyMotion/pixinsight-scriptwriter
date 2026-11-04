// Headless test harness. Run with: psw.py test <Slug> <N>
// The runner substitutes __LOG_PATH__ and __SCRIPT_PATH__.
#engine v8
#define PSW_TEST_MODE
#include "__SCRIPT_PATH__"

var PSW_LOG = "__LOG_PATH__";
var results = { ok: true, checks: [], errors: [] };

function check( name, cond, detail )
{
   results.checks.push( { name: name, pass: !!cond, detail: detail === undefined ? "" : String( detail ) } );
   if ( !cond )
      results.ok = false;
}

function makeSyntheticImage( id, w, h, channels )
{
   // Sky background + gaussian noise + a few stars + a soft nebula blob.
   var win = new ImageWindow( w, h, channels, 32, true, channels > 1, id );
   var P = new PixelMath;
   P.expression =
      "0.08 + 0.01*gauss() " +
      "+ 0.25*exp(-((x()-0.5*w())^2+(y()-0.5*h())^2)/(2*(0.15*w())^2)) " +
      "+ 0.9*exp(-((x()-0.25*w())^2+(y()-0.3*h())^2)/4) " +
      "+ 0.7*exp(-((x()-0.7*w())^2+(y()-0.6*h())^2)/3) " +
      "+ 0.5*exp(-((x()-0.4*w())^2+(y()-0.8*h())^2)/2)";
   P.useSingleExpression = true;
   P.createNewImage = false;
   P.truncate = true;
   P.executeOn( win.mainView );
   return win;
}

try
{
   // 1. Parameters object works.
   var params = new PSWParameters;
   check( "parameters constructed", params !== null );

   // 2. Dialog can be constructed (catches GUI typos) - never executed here.
   var dlg = new PSWDialog( params );
   check( "dialog constructed", dlg !== null );

   // 3. Engine runs on a mono and an RGB synthetic image.
   [ 1, 3 ].forEach( function( ch )
   {
      var win = makeSyntheticImage( "psw_test_" + ch, 512, 384, ch );
      var before = win.mainView.image.median();
      var t0 = Date.now();
      var out = PSWEngine.run( win.mainView, params );
      var after = win.mainView.image.median();
      check( "engine ran on " + ch + "-channel image", true,
             "median " + before.toFixed( 5 ) + " -> " + after.toFixed( 5 ) +
             ", " + (Date.now() - t0) + " ms, out=" + JSON.stringify( out ) );
      check( "result is finite on " + ch + "-channel image", isFinite( after ) );
      // SCRIPT-SPECIFIC CHECKS GO HERE (expected direction of change, ranges...).
      win.forceClose();
   } );
}
catch ( e )
{
   results.ok = false;
   results.errors.push( String( e ) + (e && e.stack ? "\n" + e.stack : "") );
}

File.writeTextFile( PSW_LOG, JSON.stringify( results, null, 2 ) + "\n" );
